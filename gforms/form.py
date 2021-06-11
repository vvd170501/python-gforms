import json
import re
from enum import Enum
from typing import Callable, Optional, Set, Dict, List
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode

import requests
from requests.status_codes import codes
from bs4 import BeautifulSoup

from .elements_base import InputElement
from .elements import _Action, Element, Page, UserEmail, Value, parse as parse_element
from .elements import CallbackRetVal, default_callback
from .errors import ClosedForm, InfiniteLoop, ParseError, FormNotLoaded, FormNotValidated, \
    InvalidURL, EditingDisabled, SigninRequired
from .util import add_indent, page_separator, list_get


# Originally based on https://gist.github.com/gcampfield/cb56f05e71c60977ed9917de677f919c


CallbackType = Callable[[InputElement, int, int], CallbackRetVal]


class Settings:
    """Settings for a form.

    Attributes:
        collect_emails: Self-explanatory.
        send_receipt: Send a copy of user's responses to their e-mail address.
            If this value is SendReceipt.ALWAYS or the user opts in
            to receive the receipt, a captcha will be required
            to submit the form.
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
        EDIT_RESPONSES = 3
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
            grades_settings = quiz[self._Index.GRADES_SETTINGS]
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
    """A result of successful form submission.

    Attributes:
        resubmit: A link to submit another response.
        summary: A link to view summary charts.
        edit: A link to edit the response.
    """

    def __init__(self, soup):
        self.resubmit = None
        self.summary = None
        self.edit = None
        # Is the div class fixed?
        container = soup.find('div', class_='freebirdFormviewerViewResponseLinksContainer')
        for link in container.find_all('a'):
            href = link.get('href', '')
            if 'viewanalytics' in href:
                self.summary = href
            elif 'edit2' in href:
                self.edit = href
            else:
                self.resubmit = href


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

    url: Optional[str]
    name: Optional[str]
    title: Optional[str]
    description: Optional[str]
    pages: Optional[List[Page]]
    settings: Settings

    is_loaded: bool
    _unvalidated_elements: Set[Element]
    _no_loops: bool  # If true, the form is guaranteed to contain no loops.

    _prefilled_data: Dict[str, List[str]]
    _first_page: Optional[requests.models.Response]
    _fbzx: Optional[str]  # Doesn't need to be unique
    _history: Optional[str]
    _draft: Optional[str]

    @property
    def is_validated(self):
        """Indicates if all input elements were validated.

        If self.fill was called and did not raise an exception,
        this value will be True."""
        return len(self._unvalidated_elements) == 0 and self._no_loops

    def __init__(self):
        self._clear()

    def load(self, url, session: Optional[requests.Session] = None):
        """Loads and parses the form.

        Args:
            url: The form url. The url should look like
                "https://docs.google.com/forms/.../viewform".
                Pre-filled links and response editing are also supported.
            session: A session which is used to load the form.
                If session is None, requests.get is used.

        Raises:
            gforms.errors.InvalidURL: The url is invalid.
            requests.exceptions.RequestException: A request failed.
            gforms.errors.ParseError: The form could not be parsed.
            gforms.errors.ClosedForm: The form is closed.
            gforms.errors.EditingDisabled: Response editing is disabled.
        """
        if session is None:
            session = requests

        self._clear()

        self.url = url
        prefilled_data, is_edit = self._parse_url(url)
        self._prefilled_data = prefilled_data

        self._first_page = session.get(self.url)

        soup = BeautifulSoup(self._first_page.text, 'html.parser')
        if self._is_closed(self._first_page):
            self.title = soup.find('title').text
            raise ClosedForm(self)
        if is_edit and self._editing_disabled(self._first_page):
            raise EditingDisabled(self)

        data = self._raw_form(soup)
        self._fbzx = self._get_fbzx(soup)
        self._history = self._get_history(soup)
        self._draft = self._get_draft(soup)
        if data is None or any(value is None for value in [self._fbzx, self._history, self._draft]):
            raise ParseError(self)

        if is_edit:
            self._prefilled_data = self._prefill_from_draft(self._draft)

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
        """Fills and validates the form using values returned by the callback.

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
        self._iterate_elements(callback, fill_optional, do_fill=True)

    def validate(self):
        """Checks if the form can be submitted successfully.

        Raises:
            gforms.errors.FormNotLoaded: The form was not loaded.
            gforms.errors.ValidationError: An element has an invalid value.
            gforms.errors.InfiniteLoop:
                The page transitions form an infinite loop.
        """
        self._iterate_elements(do_fill=False)

    def submit(
            self,
            session=None, *,
            need_receipt=False,
            captcha_handler: Optional[Callable[[requests.models.Response], str]] = None,
            emulate_history=False
    ) -> SubmissionResult:
        """Submits the form.

        The form must be loaded, (optionally) filled and validated.

        Args:
            session: see Form.load
            need_receipt:
                Effective only if settings.send_receipt is SendReceipt.OPT_IN
                If True, will throw NotImplementedError.
            captcha_handler:
                A function which accepts a Response (a page with reCAPTCHA v2)
                and returns a string (g-recaptcha-response).
                NOTE Response and Response.request contain user's input.
                It should not be passed to third-party services unprocessed,
                since this may lead to privacy or security issues.
            emulate_history:
                Use only one request to submit the form
                (two requests for multipage forms with a captcha).
                For single-page forms the behavior is unchanged.
                For multi-page forms, the data from previous pages
                (pageHistory and draftResponse) is formed locally.

        Raises:
            requests.exceptions.RequestException: A request failed.
            RuntimeError: The predicted next page differs from the real one
                or a session(s) response with an incorrect code was received.
            ValueError: A captcha handler is required, but was not provided.
            gforms.errors.SigninRequired:
                The form requires sign in, this feature is not implemented.
            gforms.errors.ClosedForm: The form is closed.
            gforms.errors.EditingDisabled: Response editing is disabled.
            gforms.errors.FormNotLoaded: The form was not loaded.
            gforms.errors.FormNotValidated: The form was not validated.
        """
        if not self.is_loaded:
            raise FormNotLoaded(self)
        if not self.is_validated:
            raise FormNotValidated(self)

        if self.settings.send_receipt is not Settings.SendReceipt.OPT_IN:
            need_receipt = self.settings.send_receipt is Settings.SendReceipt.ALWAYS
        if need_receipt and captcha_handler is None:
            raise ValueError('captcha_handler is missing')

        if self.settings.signin_required:
            raise SigninRequired(self)

        if session is None:
            session = requests

        if emulate_history:
            last_response, page, history, draft = self._emulate_history(session, need_receipt)
        else:
            page = self.pages[0]
            history = self._history
            draft = self._draft
            last_response = self._first_page  # TODO prefill with sample values (at load time?)

        captcha_response = None

        while page is not None:
            next_page = page.next_page()
            # solve the CAPTCHA to submit the form and send a receipt
            if need_receipt and next_page is None:
                captcha_response = captcha_handler(last_response)
            last_response = self._submit_page(session, page, history, draft,
                                              continue_=next_page is not None,
                                              need_receipt=need_receipt,
                                              captcha_response=captcha_response)
            soup = BeautifulSoup(last_response.text, 'html.parser')
            history = self._get_history(soup)
            draft = self._get_draft(soup)
            if next_page is None and history is None:
                return SubmissionResult(soup)
            if next_page is None or history is None or \
                    next_page.index != int(history.rsplit(',', 1)[-1]):
                raise RuntimeError('Incorrect next page', self, last_response, next_page)
            page = next_page

    def _clear(self):
        self.url = None
        self.name = None
        self.title = None
        self.description = None
        self.pages = None
        self.settings = Settings()
        self.is_loaded = False

        self._prefilled_data = {}
        self._first_page = None

        self._unvalidated_elements = set()
        self._no_loops = True  # The form is guaranteed to contain no loops.

        self._fbzx = None  # Doesn't need to be unique
        self._history = None
        self._draft = None

    @staticmethod
    def _parse_url(url: str):
        """Checks the URL and extracts prefilled data."""
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
        is_edit = 'edit2' in query
        return prefilled_data, is_edit

    @staticmethod
    def _response_url(url: str):
        url_data = list(urlsplit(url))
        url_data[2] = re.sub(r'viewform.*?$', 'formResponse', url_data[2])  # path
        original_query = parse_qs(url_data[3])
        query = {}
        # If 'edit2' is removed, it is possible to edit a response when editing is restricted.
        # This may be eventually fixed by Google.
        if 'edit2' in original_query:
            query['edit2'] = original_query['edit2']
        url_data[3] = urlencode(query, doseq=True)
        return urlunsplit(url_data)

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
            self._email_input.bind(self)
            self.pages[0].append(self._email_input)
            self._email_input.prefill(self._prefilled_data)

        if form[self._FormIndex.ELEMENTS] is None:
            return

        for elem in form[self._FormIndex.ELEMENTS]:
            el_type = Element.Type(elem[Element._Index.TYPE])
            if el_type == Element.Type.PAGE:
                self.pages.append(Page.parse(elem).with_index(len(self.pages)))
                # A multipage form with no input elements still needs to be validated.
                # A single-page form with action elements doesn't need additional validation
                # (actions are ignored).
                self._no_loops = False
                continue
            element = parse_element(elem)
            element.bind(self)
            self.pages[-1].append(element)
            if isinstance(element, InputElement):
                element.prefill(self._prefilled_data)
        self._resolve_actions()

    def _iterate_elements(
            self,
            callback: Optional[CallbackType] = None,
            fill_optional=False,
            *,
            do_fill
    ):
        """(optionally) fills and validates the elements."""
        if not self.is_loaded:
            raise FormNotLoaded(self)

        page = self.pages[0]
        pages_to_submit = {page}
        while page is not None:
            # use real element index or it would be better to count only input elements?
            for elem_index, elem in enumerate(page.elements):
                if not isinstance(elem, InputElement):
                    continue
                if do_fill:
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

                if elem in self._unvalidated_elements:
                    elem.validate()

            page = page.next_page()
            if page in pages_to_submit:
                # It is possible to create a form in which any choice will lead to an infinite loop.
                # These cases are not detected (add a separate public method?)
                raise InfiniteLoop(self)
            pages_to_submit.add(page)
        self._no_loops = True

    def _resolve_actions(self):
        mapping = {page.id: page for page in self.pages}
        mapping[_Action.SUBMIT] = Page.SUBMIT
        for (page, next_page) in zip(self.pages, self.pages[1:] + [None]):
            page._resolve_actions(next_page, mapping)

    def _emulate_history(self, session, update_last_response):
        history = self._history.split(',')  # ['0']
        draft = json.loads(self._draft)  # basic draft, without prefill/edit: [None, None, fbzx]
        draft[0] = None  # may contain prefilled values
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

        last_page = self.pages[0]
        prev_page = None
        last_response = self._first_page

        while True:
            next_page = last_page.next_page()
            if next_page is None:
                if update_last_response and last_page is not self.pages[0]:
                    # TODO fill the form with sample values to get the last_response?
                    #   (see captcha_handler note in Form.submit)
                    last_response = self._submit_page(session,
                                                      prev_page,
                                                      ','.join(history[:-1]),
                                                      json.dumps(draft),
                                                      continue_=True, need_receipt=False)
                return last_response, last_page, ','.join(history), json.dumps(draft)
            history.append(str(next_page.index))
            if draft[0] is None:
                draft[0] = last_page.draft()
            else:
                draft[0] += last_page.draft()
            prev_page = last_page
            last_page = next_page

    def _submit_page(self, session, page, history, draft, *,
                     continue_, need_receipt, captcha_response=None):
        payload = page.payload()

        payload['fbzx'] = self._fbzx
        if continue_:
            payload['continue'] = 1
        payload['pageHistory'] = history
        payload['draftResponse'] = draft
        if need_receipt and not continue_:
            payload['g-recaptcha-response'] = captcha_response

        url = self._response_url(self.url)
        response = session.post(url, data=payload)
        if self._is_closed(response):
            raise ClosedForm(self)
        if self._editing_disabled(response):
            raise EditingDisabled(self)
        if response.status_code != 200:
            if response.status_code == codes.unauthorized:
                raise SigninRequired(self)
            raise RuntimeError('Invalid response code', response)
        return response

    @staticmethod
    def _prefill_from_draft(draft: str):
        draft = json.loads(draft)
        if draft[0] is None:
            return {}
        prefilled_data = {}
        for entry in draft[0]:
            prefilled_data[entry[1]] = entry[2]  # Use an index class for draft?
        email = list_get(draft, 6, None)
        if email is not None:
            prefilled_data[UserEmail.ENTRY_ID] = [email]
        return prefilled_data

    @staticmethod
    def _is_closed(page):
        return page.url.endswith('closedform')

    @staticmethod
    def _editing_disabled(page):
        return page.url.endswith('editingdisabled')

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
