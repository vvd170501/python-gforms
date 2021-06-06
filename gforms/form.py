import json
import re
from enum import Enum
from typing import Callable, Optional, List
from urllib.parse import urlsplit, urlunsplit, parse_qs

import requests
from bs4 import BeautifulSoup

from .elements_base import InputElement
from .elements import _Action, Element, Page, UserEmail, Value, parse as parse_element
from .elements import CallbackRetVal, default_callback
from .errors import ClosedForm, InfiniteLoop, ParseError, FormNotLoaded, FormNotValidated, InvalidURL
from .util import add_indent, page_separator, list_get

# based on https://gist.github.com/gcampfield/cb56f05e71c60977ed9917de677f919c


CallbackType = Callable[[InputElement, int, int], CallbackRetVal]


class Settings:
    """Settings for a form.

    Attributes:
        collect_emails: Self-explanatory.
        send_receipt: Send a copy of user's responses to their e-mail address.
            If this value is SendReceipt.ALWAYS or the user opts in
            to receive the receipt, a captcha will be required
            to submit the form.
            NOTE Captcha handling is not implemented.
        signin_required: When Ture, the user must use a google account
            to submit this form. Only one response can be submitted.
        show_summary: Whether the user is allowed to view response stats.
        edit_responses: Self-explanatory.
        show_progressbar: Self-explanatory.
        shuffle_questions: Self-explanatory.
            It seems that the order of parsed questions isn't affected.
            However, shuffle_options on elements actually shuffles the options.
        show_resubmit_link: Self-explanatory.
        confirmation_msg:
            The message which is shown after a successful submission.
        is_quiz: Self-explanatory.
        immediate_grades: The user may view their grades immediately.
        show_missed: "Identify which questions were answered incorrectly"
            (from the form creation page).
        show_correct_answers: Self-explanatory.
        show_points: Self-explanatory.
    """

    class _Index:
        FIRST_BLOCK = 2
        SECOND_BLOCK = 10
        QUIZ_BLOCK = 16

        # First block
        CONFIRMATION_MSG = 0
        SHOW_RESUBMIT_LINK = 1
        SHOW_SUMMARY = 2
        EDIT_RESPONSES = 3  # !!!
        # Second block. The first 4 elements may be None
        SHOW_PROGRESSBAR = 0
        SIGNIN_REQUIRED = 1
        SHUFFLE_QUESTIONS = 2
        RECEIPT = 3
        COLLECT_EMAILS = 4
        # Quiz block
        # It's possible to create a form with IMMEDIATE_GRADES ==  COLLECT_EMAILS == 0
        GRADES_SETTINGS = 0
        SHOW_MISSED = 2
        SHOW_CORRECT = 3
        SHOW_POINTS = 4
        IMMEDIATE_GRADES = 1
        IS_QUIZ = 2

    class SendReceipt(Enum):
        # NOTE Captcha is required to send a receipt
        UNUSED = None  # value is None when collect_emails is False
        OPT_IN = 1
        NEVER = 2
        ALWAYS = 3

    def parse(self, form_data):
        # any block may be missing
        first_block = form_data[self._Index.FIRST_BLOCK]
        second_block = form_data[self._Index.SECOND_BLOCK]
        quiz = list_get(form_data, self._Index.QUIZ_BLOCK, None)

        if first_block is not None:
            self.confirmation_msg = first_block[self._Index.CONFIRMATION_MSG] or None
            self.show_resubmit_link = bool(first_block[self._Index.SHOW_RESUBMIT_LINK])
            self.show_summary = bool(first_block[self._Index.SHOW_SUMMARY])
            self.edit_responses = bool(first_block[self._Index.EDIT_RESPONSES])
        if second_block is not None:
            self.show_progressbar = bool(second_block[self._Index.SHOW_PROGRESSBAR])
            self.signin_required = bool(second_block[self._Index.SIGNIN_REQUIRED])
            self.shuffle_questions = bool(second_block[self._Index.SHUFFLE_QUESTIONS])
            self.send_receipt = self.SendReceipt(second_block[self._Index.RECEIPT])
            self.collect_emails = bool(second_block[self._Index.COLLECT_EMAILS])
        if quiz is not None and len(quiz) > self._Index.IS_QUIZ:
            self.is_quiz = bool(quiz[self._Index.IS_QUIZ])
        if self.is_quiz:
            self.immediate_grades = bool(quiz[self._Index.IMMEDIATE_GRADES])
            grades_settings = quiz[self._Index.IMMEDIATE_GRADES]
            self.show_missed = bool(grades_settings[self._Index.SHOW_MISSED])
            self.show_correct_answers = bool(grades_settings[self._Index.SHOW_CORRECT])
            self.show_points = bool(grades_settings[self._Index.SHOW_POINTS])

    def __init__(self):
        """Initializes all settings with a default value."""
        self.collect_emails = False
        self.send_receipt = self.SendReceipt.UNUSED

        self.signin_required = False

        self.show_summary = False
        self.edit_responses = False

        self.show_progressbar = False
        self.shuffle_questions = False
        self.show_resubmit_link = True

        self.confirmation_msg: Optional[str] = None

        self.is_quiz = False
        self.immediate_grades = True

        self.show_missed = True
        self.show_correct_answers = True
        self.show_points = True


class SubmissionResult:
    pass  # !!


class Form:
    """A Google Form wrapper.

    Attributes:
        url: URL of the form.
        name: Name of the form (== document name, not shown on the submission page).
        title: Title of the form.
        description: Description of the form.
        pages: List of form pages.
        settings: The form settings.
        is_loaded: Indicates if this form was properly loaded and parsed.
        is_validated:
            Indicates if this form was successfully validated and may be submitted.
    """

    @property
    def is_validated(self):
        """Indicates if all input elements were validated.

        If self.fill was called and did not raise an exception,
        this value will be True."""
        return len(self._unvalidated_elements) == 0

    class _DocIndex:
        FORM = 1
        NAME = 3
        URL = 14  # Unused. Is the index constant?
        SIGNIN_REQUIRED = 18  # Duplicate or has other meaning?

    class _FormIndex:
        DESCRIPTION = 0
        ELEMENTS = 1
        STYLE = 4  # Not implemented
        TITLE = 8

    def __init__(self):
        self.url = None
        self.name = None
        self.title = None
        self.description = None
        self.pages = None
        self.settings = Settings()
        self.is_loaded = False

        self._prefilled_data = {}

        self._unvalidated_elements = set()

        self._fbzx = None
        self._history = None
        self._draft = None

    def load(self, url, session: Optional[requests.Session] = None):
        """Loads and parses the form.

        Args:
            url: The form url. The url should look like
                "https://docs.google.com/forms/.../viewform".
                Pre-filled links are also supported.
            session: A session which is used to load the form.
                If session is None, requests.get is used.

        Raises:
            gforms.errors.InvalidURL: The url is invalid.
            requests.exceptions.RequestException: A request failed.
            gforms.errors.ParseError: The form could not be parsed.
            gforms.errors.ClosedForm: The form is closed.
        """
        if session is None:
            session = requests

        # load() may fail, in this case form data will be inconsistent
        self.is_loaded = False
        self._unvalidated_elements = set()

        url, prefilled_data = self._parse_url(url)
        self.url = url
        self._prefilled_data = prefilled_data

        page = session.get(self.url)
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
        self.is_loaded = True

    def to_str(self, indent=0, include_answer=False):
        """Returns a text representation of the form.

        Args:
            indent: The indent for pages and elements.
            include_answer: A boolean,
                indicating if the output should contain the answers.

        Returns:
            A (multiline) string representation of this form.
        """
        if not self.is_loaded:
            raise FormNotLoaded(self)

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

        You may also fill individual elements using their set_value method.
        In this ase, you will need to call Form.validate manually.

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
            gforms.errors.FormNotLoaded: The form was not loaded.
            gforms.errors.InfiniteLoop: The chosen values cannot be submitted,
                because the page transitions form an infinite loop.
            NotImplementedError: The default callback was used for an unsupported element.
        """
        if not self.is_loaded:
            raise FormNotLoaded(self)

        page = self.pages[0]
        pages_to_submit = {page}
        while page is not None:
            # use real element index or it would be better to count only input elements?
            for elem_index, elem in enumerate(page.elements):
                if not isinstance(elem, InputElement):
                    continue
                value: CallbackRetVal = Value.DEFAULT
                if callback is not None:
                    value = callback(elem, page.index, elem_index)
                    if value is None:  # missing return statement in the callback
                        raise ValueError('Callback returned an invalid value (None).'
                                         ' Is it missing a return statement?')

                if value is Value.DEFAULT:
                    if elem.required or fill_optional:
                        value = default_callback(elem, page.index, elem_index)
                    else:
                        value = value.EMPTY

                if value is not Value.UNCHANGED:
                    elem.set_value(value)
                # Still need to validate (see InputElement.prefill).
                if elem in self._unvalidated_elements:
                    elem.validate()

            page = page.next_page()
            if page in pages_to_submit:
                # It is possible to create a form in which any choice will lead to an infinite loop.
                # These cases are not detected (add a separate public method?)
                raise InfiniteLoop(self)
            pages_to_submit.add(page)

    def validate(self):
        """Validate all updated elements.

        Raises:
            gforms.errors.ValidationError: An element has an invalid value.
        """
        for elem in list(self._unvalidated_elements):
            elem.validate()

    def submit(self, session=None, need_receipt=False, emulate_history=False) -> List[requests.models.Response]:
        """Submits the form.

        The form must be loaded, (optionally) filled and validated.

        Args:
            session: see Form.load
            need_receipt:
                Effective only if settings.send_receipt is SendReceipt.OPT_IN
                If True, will throw NotImplementedError.
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
                or a session(s) response with an incorrect code was received.
            gforms.errors.ClosedForm: The form is closed.
            gforms.errors.FormNotLoaded: The form was not loaded.
            gforms.errors.FormNotValidated: The form was not validated.
        """
        if not self.is_loaded:
            raise FormNotLoaded(self)
        if not self.is_validated:
            raise FormNotValidated(self)

        if self.settings.signin_required:
            # TODO auth?
            raise NotImplementedError('A Google account is required to submit this form')

        if self.settings.send_receipt is not Settings.SendReceipt.OPT_IN:
            need_receipt = self.settings.send_receipt is Settings.SendReceipt.ALWAYS

        if need_receipt:
            # TODO is it possible to use a callback?
            raise NotImplementedError('Need to solve a captcha to submit the form')

        if session is None:
            session = requests

        if emulate_history:
            last_page, history, draft = self._emulate_history()
            return [self._submit_page(session, last_page, history, draft, False)]

        res = []
        page = self.pages[0]
        history = self._history
        draft = self._draft

        while page is not None:
            next_page = page.next_page()
            sub_result = self._submit_page(session, page, history, draft, next_page is not None)
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

    @staticmethod
    def _parse_url(url: str):
        """Extracts the base url and prefilled data."""
        url_data = urlsplit(url)
        if not url_data.path.endswith('viewform'):
            raise InvalidURL(url)
        prefilled_data = {}
        query = parse_qs(url_data.query)
        if query.get('usp', [''])[0] == 'pp_url':
            prefilled_data = {
                int(key[6:]): value
                for key, value in query.items() if key.startswith('entry.')
            }
        return urlunsplit(url_data[:3]+('', '')), prefilled_data

    def _parse(self, data):
        self.name = data[self._DocIndex.NAME]
        form = data[self._DocIndex.FORM]
        self.title = form[self._FormIndex.TITLE]
        if not self.title:
            self.title = self.name
        self.description = form[self._FormIndex.DESCRIPTION]

        self.settings.parse(form)

        self.pages = [Page.first()]
        if self.settings.collect_emails:
            # Not a real element, but is displayed like one
            self._email_input = UserEmail()
            self.pages[0].append(self._email_input)
        if form[self._FormIndex.ELEMENTS] is None:
            return
        for elem in form[self._FormIndex.ELEMENTS]:
            el_type = Element.Type(elem[Element._Index.TYPE])
            if el_type == Element.Type.PAGE:
                self.pages.append(Page.parse(elem).with_index(len(self.pages)))
                continue
            element = parse_element(elem)
            element.bind(self)
            self.pages[-1].append(element)
            if isinstance(element, InputElement):
                element.prefill(self._prefilled_data)
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

        if self.settings.collect_emails:
            if len(draft) < 8:
                draft += [None] * (8 - len(draft))
            draft[6] = self._email_input._value[0]
            draft[7] = 1  # ??

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
        pattern = re.compile(r'FB_PUBLIC_LOAD_DATA_ = (\[.+\])\n;', re.S)
        for script in scripts:
            if script.string is None:
                continue
            match = pattern.search(script.string)
            if match:
                return json.loads(match.group(1))
        return None
