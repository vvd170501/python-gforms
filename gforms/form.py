import json
import re
from typing import Callable

from bs4 import BeautifulSoup as BS

from .elements import ElementType, Element, InputElement, Page, Value
from .elements import CallbackRetval, default_callback
from .errors import InfiniteLoop
from .util import Action, add_indent, SEP_WIDTH


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
        self.title = None
        self.description = None
        self.pages = None

    def load(self, http, resend=False):
        # does resend actually matter?
        params = {'usp': 'form_confirm'} if resend else None
        page = http.get(self.url, params=params)
        soup = BS(page.text, 'html.parser')
        self._fbzx = self._get_fbzx(soup)
        self._history = self._get_history(soup)
        self._draft = self._get_draft(soup)
        data = self._raw_form(soup)
        self.name = data[self.Index.NAME]  # not shown anywhere (?)
        form = data[self.Index.FORM]
        self.title = form[self.Index.TITLE]
        self.description = form[self.Index.DESCRIPTION]
        self.pages = [Page(0)]

        for elem in form[self.Index.FIELDS]:
            el_type = ElementType(elem[Element.Index.TYPE])
            if el_type == ElementType.PAGE:
                self.pages.append(Page(len(self.pages), elem))
                continue
            self.pages[-1].append(Element.parse(elem))
        self._resolve_actions()

    def to_str(self, indent=0, include_answer=False):
        SEPARATOR = '=' * SEP_WIDTH
        if self.description:
            title = f'{self.title}\n{self.description}'
        else:
            title = self.title
        lines = '\n'.join(
            [SEPARATOR] +
            [
                add_indent(page.to_str(indent=indent, include_answer=include_answer), indent) +
                '\n' + SEPARATOR
                for page in self.pages
            ]
        )
        return f'{title}\n{lines}'

    def fill(
                self,
                callback: Callable[[InputElement, int, int], CallbackRetval] = None,
                fill_optional=False
            ):
        """
        fill_optional: fill optional elements if callback returned Value.DEFAULT
        """
        for page in self.pages:
            for elem_index, elem in enumerate(page.elements):
                if not isinstance(elem, InputElement):
                    continue
                value = Value.EMPTY
                if callback is not None:
                    value = callback(elem, page.index, elem_index)
                    if value is None:  # just in case (if callback doesn't return anything)
                        value = Value.DEFAULT
                if (elem.required or fill_optional) and \
                        (callback is None or value is Value.DEFAULT):
                    value = default_callback(elem, page.index, elem_index)
                elem.set_value(value)

        page = self.pages[0]
        pages_to_submit = {page}
        while page is not None:
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
            soup = BS(sub_result.text, 'html.parser')
            history = self._get_history(soup)
            draft = self._get_draft(soup)
            if page is None and history is None:
                break
            if page is None or history is None or page.index != int(history.rsplit(',', 1)[-1]):
                raise RuntimeError('Incorrect next page', self, res, page)
        return res

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

    def _resolve_actions(self):
        mapping = {page.id: page for page in self.pages}
        mapping[Action.SUBMIT] = Page.SUBMIT()
        for (page, next_page) in zip(self.pages, self.pages[1:] + [None]):
            page._resolve_actions(next_page, mapping)

    @staticmethod
    def _get_fbzx(soup):
        return soup.find('input', {'name': 'fbzx'})['value']

    @staticmethod
    def _get_history(soup):
        history = soup.find('input', {'name': 'pageHistory'})
        if history is None:
            return None
        return history['value']

    @staticmethod
    def _get_draft(soup):
        draft = soup.find('input', {'name': 'draftResponse'})
        if draft is None:
            return None
        return draft['value']

    @staticmethod
    def _raw_form(soup):
        script = soup.find_all('script')[3].string
        pattern = re.compile(r'FB_PUBLIC_LOAD_DATA_ = (\[.+\])\n;', re.S)
        data = json.loads(pattern.search(script).group(1))
        return data
