import json
import re
from typing import Callable, Optional, List

import requests
from bs4 import BeautifulSoup

from .elements_base import InputElement
from .elements import _Action, Element, Page, Value, parse as parse_element
from .elements import CallbackRetVal, default_callback
from .errors import ClosedForm, InfiniteLoop, ParseError, FormNotLoaded, FormNotFilled
from .util import add_indent, page_separator


# based on https://gist.github.com/gcampfield/cb56f05e71c60977ed9917de677f919c


CallbackType = Callable[[InputElement, int, int], CallbackRetVal]


class Form:
    """A Google Form wrapper.

    Attributes:
        url: URL of the form.
        name: Name of the form (== document name, not shown on the submission page).
        title: Title of the form.
        description: Description of the form.
        pages: List of form pages.
    """

    class _Index:
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
        self._is_loaded = False
        self._is_filled = False

    def load(self, http: Optional[requests.Session] = None):
        """Loads and parses the form.

        Args:
            http: A session which is used to load the form.
                By default, requests.get is used.

        Raises:
            requests.exceptions.RequestException: A request failed.
            gforms.errors.ParseError: The form could not be parsed.
            gforms.errors.ClosedForm: The form is closed.
        """
        if http is None:
            http = requests

        # load() may fail, in this case form data will be inconsistent
        self._is_loaded = False
        self._is_filled = False

        page = http.get(self.url)
        soup = BeautifulSoup(page.text, 'html.parser')
        if self._is_closed(page):
            self.title = soup.find('title').text
            raise ClosedForm(self)

        data = self._raw_form(soup)
        self._fbzx = self._get_fbzx(soup)
        self._history = self._get_history(soup)
        self._draft = self._get_draft(soup)
        if data is None or any(value is None for value in [self._fbzx, self._history, self._draft]):
            raise ParseError(self)
        self._parse(data)
        self._is_loaded = True

    def to_str(self, indent=0, include_answer=False):
        """Returns a text representation of the form.

        Args:
            indent: The indent for pages and elements.
            include_answer: A boolean,
                indicating if the output should contain the answers.

        Returns:
            A (multiline) string representation of this form.
        """
        if not self._is_loaded:
            raise FormNotLoaded(self)

        if not self._is_filled:
            include_answer = False

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
                callback: Optional[CallbackType] = None,
                fill_optional=False
            ):
        """Fills the form using values returned by the callback.

        If callback is None, the default callback (see below) is used.

        For an example implementation of a callback,
        see gforms.elements.default_callback.

        For types and values accepted by an element, see its set_value method.

        Args:
            callback: The callback which returns values for elements.
                If the callback returns gforms.elements.Value.DEFAULT
                for an element, then the default callback
                is used for this element.

            fill_optional:
                Whether or not optional elements should be filled
                by the default callback.

        Raises:
            ValueError: The callback returned an invalid value.
            gforms.errors.ElementError:
                The callback returned an unexpected value for an element
            gforms.errors.ValidationError: The form cannot be submitted later
                if an element is filled with the callback return value
            gforms.errors.InfiniteLoop: The chosen values cannot be submitted,
                because the page transitions form an infinite loop.
            NotImplementedError: The default callback was used for an unsupported element.
        """
        if not self._is_loaded:
            raise FormNotLoaded(self)
        self._is_filled = False

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
                        raise ValueError('Callback returned an invalid value (None).'
                                         ' Is it missing a return statement?')

                if callback is None and (elem.required or fill_optional) or value is Value.DEFAULT:
                    value = default_callback(elem, page.index, elem_index)
                elem.set_value(value)
                elem.validate()

            page = page.next_page()
            if page in pages_to_submit:
                # It is possible to create a form in which any choice will lead to an infinite loop.
                # These cases are not detected (add a separate public method?)
                raise InfiniteLoop(self)
            pages_to_submit.add(page)
        self._is_filled = True

    def submit(self, http=None, emulate_history=False) -> List[requests.models.Response]:
        """Submits the form.

        Args:
            http: see Form.load
            emulate_history: (Experimental)
                Use only one request for submitting the form.
                For single-page forms the behavior is unchanged.
                For multi-page forms, the data from previous pages
                (pageHistory and draftResponse) is created locally.
                When using this option,
                some values may be submitted incorrectly, since
                the format of draftResponse is only partially known.

        Raises:
            requests.exceptions.RequestException: A request failed.
            RuntimeError: The predicted next page differs from the real one
                or a http(s) response with an incorrect code was received.
            gforms.errors.ClosedForm: The form is closed.
        """
        if not self._is_filled:
            raise FormNotFilled(self)

        if http is None:
            http = requests

        if emulate_history:
            last_page, history, draft = self._emulate_history()
            return [self._submit_page(http, last_page, history, draft, False)]

        res = []
        page = self.pages[0]
        history = self._history
        draft = self._draft

        while page is not None:
            next_page = page.next_page()
            sub_result = self._submit_page(http, page, history, draft, next_page is not None)
            res.append(sub_result)
            if sub_result.status_code != 200:
                raise RuntimeError('Invalid response code', res)
            soup = BeautifulSoup(sub_result.text, 'html.parser')
            history = self._get_history(soup)
            draft = self._get_draft(soup)
            if next_page is None and history is None:
                break  # submitted successfully
            if next_page is None or history is None or \
                    next_page.index != int(history.rsplit(',', 1)[-1]):
                raise RuntimeError('Incorrect next page', self, res, next_page)
            page = next_page
        return res

    def _parse(self, data):
        self.name = data[self._Index.NAME]
        form = data[self._Index.FORM]
        self.title = form[self._Index.TITLE]
        if not self.title:
            self.title = self.name
        self.description = form[self._Index.DESCRIPTION]
        self.pages = [Page.first()]

        if form[self._Index.FIELDS] is None:
            return
        for elem in form[self._Index.FIELDS]:
            el_type = Element.Type(elem[Element._Index.TYPE])
            if el_type == Element.Type.PAGE:
                self.pages.append(Page.parse(elem).with_index(len(self.pages)))
                continue
            self.pages[-1].append(parse_element(elem))
        self._resolve_actions()

    def _resolve_actions(self):
        mapping = {page.id: page for page in self.pages}
        mapping[_Action.SUBMIT] = Page.SUBMIT
        for (page, next_page) in zip(self.pages, self.pages[1:] + [None]):
            page._resolve_actions(next_page, mapping)

    def _emulate_history(self):
        last_page = self.pages[0]
        history = self._history.split(',')  # ['0']
        draft = json.loads(self._draft)  # [None, None, fbzx]
        # draft[0] should be None or non-empty,
        # but submission works with an empty value (on 25.05.21)

        # For some unfilled elements, draft values should be [""],
        # but if the corresponding entries are not included into the draft,
        # the form is still accepted

        while True:
            next_page = last_page.next_page()
            if next_page is None:
                return last_page, ','.join(history), json.dumps(draft)
            history.append(str(next_page.index))
            if draft[0] is None:
                draft[0] = last_page.draft()
            else:
                draft[0] += last_page.draft()
            last_page = next_page

    def _submit_page(self, http, page, history, draft, continue_):
        payload = page.payload()

        payload['fbzx'] = self._fbzx
        if continue_:
            payload['continue'] = 1
        payload['pageHistory'] = history
        payload['draftResponse'] = draft

        url = re.sub(r'(.+)viewform.*', r'\1formResponse', self.url)
        page = http.post(url, data=payload)
        if self._is_closed(page):
            raise ClosedForm(self)
        return page

    @staticmethod
    def _is_closed(page):
        return page.url.endswith('closedform')

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
        scripts = soup.find_all('script')
        if len(scripts) < 4:
            return None
        pattern = re.compile(r'FB_PUBLIC_LOAD_DATA_ = (\[.+\])\n;', re.S)
        match = pattern.search(scripts[3].string)
        if match is None:
            return None
        data = json.loads(match.group(1))
        return data
