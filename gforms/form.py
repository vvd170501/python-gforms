import json
import re
from typing import Callable, Optional

from bs4 import BeautifulSoup

from .elements_base import InputElement
from .elements import Action, Element, Page, Value, parse as parse_element
from .elements import CallbackRetVal, default_callback
from .errors import ClosedForm, InfiniteLoop, ParseError
from .util import add_indent, page_separator


# based on https://gist.github.com/gcampfield/cb56f05e71c60977ed9917de677f919c


class Form:
    class Index:
        FORM = 1
        DESCRIPTION = 0
        FIELDS = 1
        TITLE = 8
        NAME = 3  # top-level
        URL = 14  # top-level, index may change?

    def __init__(self, url):
        self.url = url
        self._fbzx = None
        self._history = None
        self._draft = None
        self.name = None
        self.title = None
        self.description = None
        self.pages = None

    def load(self, http, resend=False):
        # does resend actually matter?
        params = {'usp': 'form_confirm'} if resend else None
        page = http.get(self.url, params=params)
        soup = BeautifulSoup(page.text, 'html.parser')
        if page.url.endswith('closedform'):
            self.title = soup.find('title').text
            raise ClosedForm(self)
        self._fbzx = self._get_fbzx(soup)
        if self._fbzx is None:
            raise ParseError(self)
        self._history = self._get_history(soup)
        self._draft = self._get_draft(soup)
        data = self._raw_form(soup)
        self._parse(data)

    def to_str(self, indent=0, include_answer=False):
        if self.description:
            title = f'{self.title}\n{self.description}'
        else:
            title = self.title
        separator = page_separator(indent)
        lines = '\n'.join(
            [separator] +
            [
                add_indent(page.to_str(indent=indent, include_answer=include_answer), indent) +
                '\n' + separator
                for page in self.pages
            ]
        )
        return f'{title}\n{lines}'

    def fill(
                self,
                callback: Optional[Callable[[InputElement, int, int], CallbackRetVal]] = None,
                fill_optional=False
            ):
        """
        fill_optional: fill optional elements if callback returned Value.DEFAULT
        """
        page = self.pages[0]
        pages_to_submit = {page}
        while page is not None:
            # use real element index or it would be better to count only input elements?
            for elem_index, elem in enumerate(page.elements):
                if not isinstance(elem, InputElement):
                    continue
                value: CallbackRetVal = Value.EMPTY
                if callback is not None:
                    value = callback(elem, page.index, elem_index)
                    if value is None:  # missing return statement in the callback
                        raise ValueError('Callback returned an invalid value (None)')

                if callback is None and (elem.required or fill_optional) or value is Value.DEFAULT:
                    value = default_callback(elem, page.index, elem_index)
                elem.set_value(value)
                elem.validate()

            page = page.next_page()
            if page in pages_to_submit:
                raise InfiniteLoop(self)
            pages_to_submit.add(page)

    def submit(self, http):

        res = []
        page = self.pages[0]
        history = self._history
        draft = self._draft

        # Compose pageHistory and draftResponse manually?
        # In this case, 1-2 requests may be enough
        while page is not None:
            next_page = page.next_page()
            sub_result = self._submit_page(http, page, history, draft, next_page is not None)
            page = next_page
            res.append(sub_result)
            if sub_result.status_code != 200:
                raise RuntimeError('Invalid response code', res)
            soup = BeautifulSoup(sub_result.text, 'html.parser')
            history = self._get_history(soup)
            draft = self._get_draft(soup)
            if page is None and history is None:
                break
            if page is None or history is None or page.index != int(history.rsplit(',', 1)[-1]):
                raise RuntimeError('Incorrect next page', self, res, page)
        return res

    def _parse(self, data):
        self.name = data[self.Index.NAME]
        form = data[self.Index.FORM]
        self.title = form[self.Index.TITLE]
        if not self.title:
            self.title = self.name
        self.description = form[self.Index.DESCRIPTION]
        self.pages = [Page.first()]

        if form[self.Index.FIELDS] is None:
            return
        for elem in form[self.Index.FIELDS]:
            el_type = Element.Type(elem[Element.Index.TYPE])
            if el_type == Element.Type.PAGE:
                self.pages.append(Page.parse(elem).with_index(len(self.pages)))
                continue
            self.pages[-1].append(parse_element(elem))
        self._resolve_actions()

    def _resolve_actions(self):
        mapping = {page.id: page for page in self.pages}
        mapping[Action.SUBMIT] = Page.SUBMIT
        for (page, next_page) in zip(self.pages, self.pages[1:] + [None]):
            page.resolve_actions(next_page, mapping)

    def _submit_page(self, http, page, history, draft, continue_):
        payload = {}
        for elem in page.elements:
            if not isinstance(elem, InputElement):
                continue
            payload.update(elem.payload())

        payload['fbzx'] = self._fbzx
        if continue_:
            payload['continue'] = 1
        payload['pageHistory'] = history
        payload['draftResponse'] = draft

        url = re.sub(r'(.+)viewform.*', r'\1formResponse', self.url)
        return http.post(url, data=payload)

    @staticmethod
    def _get_input(soup, name):
        elem = soup.find('input', {'name': name})
        if elem is None:
            return None
        return elem['value']

    @staticmethod
    def _get_fbzx(soup):
        return Form._get_input(soup, 'fbzx')

    @staticmethod
    def _get_history(soup):
        return Form._get_input(soup, 'pageHistory')

    @staticmethod
    def _get_draft(soup):
        return Form._get_input(soup, 'draftResponse')

    @staticmethod
    def _raw_form(soup):
        script = soup.find_all('script')[3].string
        pattern = re.compile(r'FB_PUBLIC_LOAD_DATA_ = (\[.+\])\n;', re.S)
        data = json.loads(pattern.search(script).group(1))
        return data
