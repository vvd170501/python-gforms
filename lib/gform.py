import json
import re
from typing import Callable

from bs4 import BeautifulSoup as BS

from .elements import ActChoiceInputElement, ElementType, Element, InputElement, Page, Value
from .elements import CallbackRetval, default_callback
from .util import Action, add_indent, SEP_WIDTH


# based on https://gist.github.com/gcampfield/cb56f05e71c60977ed9917de677f919c


class GForm:
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
        self._history = None  # TODO !!
        self._draft = None  # TODO !!
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
                callback: Callable[[Element, int, int], CallbackRetval] = None,
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

    def submit(self, http):
        sub_url = re.sub(r'(.+)viewform.*', r'\1formResponse', self.url)

        def submit_page(page, history, draft):
            # TODO parse previous page for history and draft
            next_page = page.next_page
            payload = {}
            for elem in page.elements:
                if not isinstance(elem, InputElement):
                    continue
                payload.update(elem.payload())
                if isinstance(elem, ActChoiceInputElement):
                    next_page = next_page  # TODO !!

###############################################################################################################
#                if elem.value is Value.EMPTY and elem.required:
#                    raise RuntimeError(f'No value for {elem.name}')
#                if isinstance(elem, ChoiceInputElement) and elem.other_value:  # check!!
#                    payload[field['submit_id']] = '__other_option__'
#                    payload[field['submit_id'] + '.other_option_response'] = field['value']
#                else:
#                    payload[field['submit_id']] = field['value']
###############################################################################################################
            payload['fbzx'] = self._fbzx
            if next_page is not None:
                payload['continue'] = 1
            payload['pageHistory'] = history
            payload['draftResponse'] = draft

            return http.post(sub_url, data=payload), next_page

        res = []
        next_page = self.pages[0]
        history = self._history
        draft = self._draft

        raise NotImplementedError()  # !!!

        while next_page is not None:
            sub_result, next_page = submit_page(next_page, history, draft)
            res.append(sub_result)
            if sub_result.status_code != 200:
                raise RuntimeError(res)
            if next_page is None:
                break
            soup = BS(sub_result.text, 'html.parser')
            history = None  # TODO !!
            draft = None  # TODO !!
#            ph = soup.find('input', {'name': 'pageHistory'})
#            if ph is None:
#                break  # finished?
#            next_page = int(ph['value'].rsplit(',', 1)[-1])
        return res

    def _resolve_actions(self):
        mapping = {page.id: page for page in self.pages}
        mapping[Action.SUBMIT] = Page.SUBMIT()
        for (page, next_page) in zip(self.pages, self.pages[1:] + [None]):
            page._resolve_actions(next_page, mapping)

    @staticmethod
    def _get_fbzx(soup):
        return soup.find('input', {'name': 'fbzx'})['value']

    @staticmethod
    def _raw_form(soup):
        script = soup.find_all('script')[3].string
        pattern = re.compile(r'FB_PUBLIC_LOAD_DATA_ = (\[.+\])\n;', re.S)
        data = json.loads(pattern.search(script).group(1))
        return data
