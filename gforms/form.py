import json
import re
import sys
from enum import Enum
from typing import Callable, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode

import requests
from requests.status_codes import codes
from bs4 import BeautifulSoup

from .elements_base import ImageChoiceInput, InputElement
from .elements import _Action, Image, Page, UserEmail, Value, \
                      parse as parse_element
from .elements import CallbackRetVal, default_callback
from .errors import ClosedForm, InfiniteLoop, ParseError, FormNotLoaded, FormNotValidated, \
    InvalidURL, NoSuchForm, EditingDisabled, SigninRequired
from .media import ImageObject
from .util import add_indent, deprecated, list_get, page_separator


# Originally based on https://gist.github.com/gcampfield/cb56f05e71c60977ed9917de677f919c


# TODO use TypeVar instead of Union?
CallbackType = Callable[[InputElement, int, int], CallbackRetVal]


class _ElementNames:
    FBZX = 'fbzx'
    DRAFT = 'partialResponse'
    HISTORY = 'pageHistory'


class Settings:
    """Settings for a form.

    Attributes:
        collect_emails: Self-explanatory.
        send_receipt: Send a copy of user's responses to their e-mail address.
            If this value is SendReceipt.ALWAYS or the user opts in
            to receive the receipt, a captcha will be required
            to submit the form.
        submit_once: Limit to 1 response. Implies sign-in requirement.
        signin_required: Deprecated, use Form.requires_signin instead.
            When True, the user must use a google account to submit this form.
        show_summary: Whether the user is allowed to view response stats.
        edit_responses: Self-explanatory.
        show_progressbar: Self-explanatory.
        shuffle_questions: Self-explanatory.
            It seems that the order of parsed questions isn't affected.
            However, shuffle_options on elements actually shuffles the options.
        show_resubmit_link: Self-explanatory.
        confirmation_msg:
            The message which is shown after a successful submission.
        disable_autosave: Disable autosave for logged-in users.
        is_quiz: Self-explanatory.
        immediate_grades: The user may view their grades (score) immediately.
        show_missed: "Identify which questions were answered incorrectly"
            (from the form creation page).
        show_correct_answers: Self-explanatory.
        show_points: Self-explanatory.
    """

    class _Index:
        FIRST_BLOCK = 2
        # index = 5: [0, 0] | None, unused?
        SECOND_BLOCK = 10
        QUIZ_BLOCK = 16

        # First block
        CONFIRMATION_MSG = 0
        SHOW_RESUBMIT_LINK = 1
        SHOW_SUMMARY = 2
        EDIT_RESPONSES = 3
        # Second block. The first 4 elements may be None
        SHOW_PROGRESSBAR = 0
        SUBMIT_ONCE = 1  # None(default/not set?) == False?
        SHUFFLE_QUESTIONS = 2
        RECEIPT = 3
        OLD_COLLECT_EMAILS = 4  # Not used anymore, seems to always be None
        DISABLE_AUTOSAVE = 5  # May be missing in old forms
        COLLECT_EMAILS = 6

        # Quiz block
        GRADES_SETTINGS = 0
        SHOW_MISSED = 2
        SHOW_CORRECT = 3
        SHOW_POINTS = 4
        IMMEDIATE_GRADES = 1
        IS_QUIZ = 2

    class CollectEmails(Enum):
        NO = 1
        VERIFIED = 2
        USER_INPUT = 3  # "Responder input" - same behavior as the old "collect emails" flag

        def __bool__(self):
            return self != self.NO

    class SendReceipt(Enum):
        UNUSED = None  # value was None with collect_emails = False (01.05.2023 - default is 2, but old forms still have None)
        OPT_IN = 1
        NEVER = 2
        ALWAYS = 3

    def parse(self, form_data):
        # any block may be missing
        first_block = form_data[self._Index.FIRST_BLOCK]
        second_block = form_data[self._Index.SECOND_BLOCK]
        quiz = list_get(form_data, self._Index.QUIZ_BLOCK, [])

        if first_block is not None:
            self.confirmation_msg = first_block[self._Index.CONFIRMATION_MSG] or None
            self.show_resubmit_link = bool(first_block[self._Index.SHOW_RESUBMIT_LINK])
            self.show_summary = bool(first_block[self._Index.SHOW_SUMMARY])
            self.edit_responses = bool(first_block[self._Index.EDIT_RESPONSES])
        if second_block is not None:
            self.show_progressbar = bool(second_block[self._Index.SHOW_PROGRESSBAR])
            self.submit_once = bool(second_block[self._Index.SUBMIT_ONCE])
            self.shuffle_questions = bool(second_block[self._Index.SHUFFLE_QUESTIONS])
            self.send_receipt = self.SendReceipt(second_block[self._Index.RECEIPT])
            self.disable_autosave = bool(list_get(second_block, self._Index.DISABLE_AUTOSAVE, False))
            self.collect_emails = self.CollectEmails(list_get(second_block, self._Index.COLLECT_EMAILS, self.CollectEmails.NO))
        if quiz is not None:
            self.is_quiz = bool(list_get(quiz, self._Index.IS_QUIZ, False))
        if self.is_quiz:
            self.immediate_grades = bool(quiz[self._Index.IMMEDIATE_GRADES])
            grades_settings = quiz[self._Index.GRADES_SETTINGS]
            self.show_missed = bool(grades_settings[self._Index.SHOW_MISSED])
            self.show_correct_answers = bool(grades_settings[self._Index.SHOW_CORRECT])
            self.show_points = bool(grades_settings[self._Index.SHOW_POINTS])

    def __init__(self):
        """Initializes all settings with a default value."""
        self.collect_emails = self.CollectEmails.NO
        self.send_receipt = self.SendReceipt.UNUSED
        self.submit_once = False
        self.show_summary = False
        self.edit_responses = False

        self.show_progressbar = False
        self.shuffle_questions = False
        self.show_resubmit_link = True
        self.confirmation_msg: Optional[str] = None
        self.disable_autosave = False

        self.is_quiz = False
        self.immediate_grades = True
        self.show_missed = True
        self.show_correct_answers = True
        self.show_points = True

    @property
    @deprecated
    def signin_required(self):
        return self.submit_once

    @property
    def show_resubmit_link(self):
        # if submit_once is set, show_resubmit_link may still be true (but meaningless)
        return self._show_resubmit_link and not self.submit_once

    @show_resubmit_link.setter
    def show_resubmit_link(self, value):
        self._show_resubmit_link = value


class SubmissionResult:
    """A result of successful form submission.

    Attributes:
        resubmit: A link to submit another response.
        summary: A link to view summary charts.
        edit: A link to edit the response.
        quiz_score: A link to view the quiz score (if available).
    """

    def __init__(self, soup):
        self.resubmit = None
        self.summary = None
        self.edit = None
        self.quiz_score = None

        link = soup.find('a')
        if link is None:
            return
        domain = urlsplit(link.get('href', '')).netloc
        if domain != 'docs.google.com':
            return  # the next link after the relevant links is 'reportabuse' (01 Mar 2022)

        container = link.find_parent('div')

        for link in container.find_all('a'):
            href = link.get('href', '')
            if 'viewanalytics' in href:
                self.summary = href
            elif 'edit2' in href:
                self.edit = href
            elif 'viewscore' in href:
                self.quiz_score = href
            else:
                self.resubmit = href


class Form:
    """A Google Form wrapper.

    Attributes:
        url: URL that was used to load the form.
        name: Name of the form (== document name, not shown on the submission page).
        title: Title of the form.
        description: Description of the form.
        pages: List of form pages.
        settings: The form settings.
        is_loaded: Indicates if this form was properly loaded and parsed.
    """

    class _DocIndex:
        FORM = 1
        NAME = 3
        URL = 14  # Unused.
        SIGNIN_REQUIRED = 18
        UNKNOWN = 19  # 26.03.2025 - seems to always be 1 in new forms, can be 1 or missing in old ones. Related to settings?

    class _FormIndex:
        DESCRIPTION = 0
        ELEMENTS = 1
        STYLE = 4  # Not implemented
        TITLE = 8

    url: Optional[str]
    name: Optional[str]
    title: Optional[str]
    description: Optional[str]
    pages: List[Page]
    settings: Settings

    is_loaded: bool

    _selected_pages: Set[Page]  # Pages which will be submitted. Used to detect loops.
    _unvalidated_pages: Set[Page]  # A subset of _selected_pages.
    # Full path == page sequence without repeating pages and with a final page.
    _found_full_path: bool

    _prefilled_data: Dict[str, List[str]]
    _first_page: Optional[requests.models.Response]
    _fbzx: Optional[str]  # Doesn't need to be unique
    _history: Optional[str]
    _draft: Optional[str]

    @property
    def requires_signin(self):
        """If True, the user must use a google account to submit this form."""
        # NOTE also should be true for forms with file upload,
        # but as of 01 May 2024, such forms have _signin_required == False for some reason.
        # These forms can't be loaded anyway (request is redirected to the sign-in page),
        # so this case is not handled.
        return self._signin_required

    @property
    def is_validated(self):
        """Indicates if this form was successfully validated and may be submitted."""
        return len(self._unvalidated_pages) == 0 and self._found_full_path

    def __init__(self):
        self._clear()

    def load(self, url, session: Optional[requests.Session] = None, resolve_images: bool = False):
        """Loads and parses the form.

        Args:
            url: The form url. Usually looks like
                "https://docs.google.com/forms/.../viewform"
                or "https://forms.gle/...".
                Pre-filled links and response editing are also supported.
            session: A session which is used to load the form.
                If session is None, requests.get is used.
            resolve_images: If true, image URLs will be parsed.
                Slows down loading of multipage forms.

        Raises:
            gforms.errors.InvalidURL: The url is not a valid form url.
            gforms.errors.NoSuchForm: The form does not exist.
            requests.exceptions.RequestException: A request failed.
            gforms.errors.ParseError: The form could not be parsed.
            gforms.errors.ClosedForm: The form is closed.
            gforms.errors.EditingDisabled: Response editing is disabled.
            gforms.errors.SigninRequired:
                The form requires sign in to be loaded.
                (most probably, it contains a file upload element).
        """
        if session is None:
            session = requests

        self._clear()  # TODO make atomic? If load/reload fails, form should keep old data

        self.url = url

        self._first_page = session.get(self.url)
        self._check_resp(self._first_page)
        prefilled_data, is_edit = self._parse_url(self._first_page.url)
        self._prefilled_data = prefilled_data

        soup = BeautifulSoup(self._first_page.text, 'html.parser')

        data = self._raw_form(soup)
        self._fbzx = self._get_fbzx(soup)
        self._history = self._get_history(soup)
        self._draft = self._get_draft(soup)
        if data is None or any(value is None for value in [self._fbzx, self._history, self._draft]):
            raise ParseError(self)

        if is_edit:
            self._prefilled_data = self._prefill_from_draft(self._draft)

        self._parse(data, resolve_images, session, soup)
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
            gforms.errors.FormNotLoaded: The form was not loaded.
            gforms.errors.ValidationError: The form cannot be submitted later
                if an element is filled with the callback return value
            gforms.errors.ElementError:
                The callback returned an unexpected value for an element
            gforms.errors.InfiniteLoop: The chosen values cannot be submitted,
                because the page transitions form an infinite loop.
            NotImplementedError: The default callback was used for an unsupported element.
            ValueError: The callback returned an invalid value.
        """
        self._iterate_elements(callback, fill_optional, do_fill=True)

    def reload(self, session: Optional[requests.Session] = None, resolve_images: bool = False):
        """Reloads the form.

        Args:
            session: See Form.load.
            resolve_images: See Form.load.

        Raises:
            FormNotLoaded
        """
        if not self.is_loaded:
            raise FormNotLoaded(self)
        self.load(self.url, session, resolve_images)

    def reset(self):
        """Resets user input and restores prefilled values.

        If the form was loaded from an edit link,
        original values are also restored.

        If the form itself was not edited,
        a call to reset() is equivalent to a reload(),
        but without any actual requests.

        Raises:
            FormNotLoaded
        """
        if not self.is_loaded:
            raise FormNotLoaded(self)
        for element in self._input_elements():
            element.prefill(self._prefilled_data)

    def clear(self):
        """Clears all element values.

        Raises:
            FormNotLoaded
        """
        if not self.is_loaded:
            raise FormNotLoaded(self)
        for element in self._input_elements():
            element.set_value(Value.EMPTY)

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
                Effective only if settings.send_receipt is Settings.SendReceipt.OPT_IN
                If True, `captcha_handler` is required.
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
            gforms.errors.NoSuchForm: The form does not exist (anymore).
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

        if self.requires_signin:
            raise SigninRequired(self)

        if session is None:
            session = requests

        if emulate_history:
            last_response, page, history, draft = self._emulate_history(session, need_receipt)
            # NOTE _fetch_page is not used for single-paged forms with captcha,
            #      last_response may contain user input (see todo below)
        else:
            page = self.pages[0]
            history = self._history
            draft = self._draft
            # TODO prefill with sample values (at load time?) (see captcha_handler note)
            #      Alternative: always use _fetch_page, even for single-page forms
            last_response = self._first_page

        captcha_response = None

        while page is not None:
            next_page = page.next_page()
            # solve the CAPTCHA to submit the form and send a receipt
            if need_receipt and next_page is None:
                captcha_response = captcha_handler(last_response)
            last_response = self._submit_page(session, page, history, draft,
                                              continue_=next_page is not None,
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
        self.pages = []
        self.settings = Settings()
        self._signin_required = False
        self.is_loaded = False

        self._prefilled_data = {}
        self._first_page = None

        self._selected_pages = set()
        self._unvalidated_pages = set()
        self._found_full_path = False

        self._fbzx = None  # Doesn't need to be unique
        self._history = None
        self._draft = None

    def _check_resp(self, resp):
        # will raise NoSuchForm for any 404/410 response. Check domain?
        if resp.status_code in [codes.not_found, codes.gone]:
            raise NoSuchForm(resp.url)
        if (
            resp.status_code == codes.unauthorized or  # submit, settings were updated
            urlsplit(resp.url).netloc == 'accounts.google.com'  # load, form contains a FileUpload
        ):
            raise SigninRequired(self)
        if self._is_closed(resp):
            if self.title is None:
                # Method is called from load(). Is the title needed?
                soup = BeautifulSoup(resp.text, 'html.parser')
                self.title = soup.find('title').text
            raise ClosedForm(self)
        if self._editing_disabled(resp):
            # If raised from Form.load, there is (?) no way to get the form title
            # without sending additional requests.
            raise EditingDisabled(self)

    @staticmethod
    def _parse_url(url: str):
        """Checks if the URL is a form url and extracts prefilled data."""
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

    def _parse(self, data, resolve_images, session, first_page_html):
        self.name = data[self._DocIndex.NAME]
        form = data[self._DocIndex.FORM]
        self.title = form[self._FormIndex.TITLE]
        if not self.title:
            self.title = self.name
        self.description = form[self._FormIndex.DESCRIPTION]

        self.settings.parse(form)
        self._signin_required = data[self._DocIndex.SIGNIN_REQUIRED]

        self._add_page(Page.first())
        self._selected_pages = {self.pages[0]}  # The first page will be submitted for any path.
        # A single-page form (even with action elements)
        # doesn't require a path check (actions are ignored).
        self._found_full_path = True

        if self.settings.collect_emails:
            # Not a real element, but is displayed like one
            self._email_input = UserEmail()
            self.pages[0].append(self._email_input)
            self._email_input.prefill(self._prefilled_data)

        if form[self._FormIndex.ELEMENTS] is None:
            return

        curr_page_images = {}

        def resolve_curr_page_images():
            if not curr_page_images:
                return
            if len(self.pages) == 1:
                soup = first_page_html
            else:
                resp = self._fetch_page(session, self.pages[-1])
                soup = BeautifulSoup(resp.text, 'html.parser')
            self._resolve_images(curr_page_images, soup)
            if curr_page_images:
                print(f'Failed to get URLs for some images on page {len(self.pages)}', file=sys.stderr)
                curr_page_images.clear()

        for elem in form[self._FormIndex.ELEMENTS]:
            element = parse_element(elem)
            if isinstance(element, Page):
                if resolve_images:
                    resolve_curr_page_images()
                self._add_page(element.with_index(len(self.pages)))
                # A multipage form with no input elements still needs to be validated
                # (Page transitions can form a loop).
                self._found_full_path = False
                continue
            self.pages[-1].append(element)
            if isinstance(element, InputElement):
                element.prefill(self._prefilled_data)
            if resolve_images:
                if isinstance(element, Image):
                    curr_page_images[element.id] = element.image
                elif isinstance(element, InputElement):
                    if element.image is not None:
                        curr_page_images[element.id] = element.image
                    if isinstance(element, ImageChoiceInput):
                        # 19.10.2022: it's not possible to attach an image to the "Other" option
                        for option in element.options:
                            if option.image is not None:
                                curr_page_images[(element.id, option.value)] = option.image
        if resolve_images:
            resolve_curr_page_images()

        self._resolve_actions()

    def _add_page(self, page: Page):
        self.pages.append(page)
        page.set_hooks(self._update_validation_state, self._invalidate_path)

    def _select_page(self, page: Page):
        if page in self._selected_pages:
            # It is possible to create a form in which any choice will lead to an infinite loop.
            # These cases are not detected (add a separate public method?)
            raise InfiniteLoop(self)
        self._selected_pages.add(page)
        if not page.is_validated:
            self._unvalidated_pages.add(page)

    def _update_validation_state(self, page: Page):
        if page not in self._selected_pages:
            return
        if page.is_validated:
            self._unvalidated_pages.discard(page)
        else:
            self._unvalidated_pages.add(page)

    def _invalidate_path(self, page: Optional[Page] = None):
        # TODO check if page.next_page() has actually been changed (?)
        #      Also, it should be possible to invalidate only part of the path
        self._selected_pages.clear()
        self._unvalidated_pages.clear()
        self._found_full_path = False

    def _resolve_actions(self):
        mapping = {page.id: page for page in self.pages}
        mapping[_Action.SUBMIT] = Page.SUBMIT
        for (page, next_page) in zip(self.pages, self.pages[1:] + [None]):
            page._resolve_actions(next_page, mapping)

    def _resolve_images(self, images: Dict[Union[int, Tuple[int, str]], ImageObject], soup: BeautifulSoup):
        # TODO do more research, maybe it's possible to generate direct image links from IDs
        #      search "google docs cosmoid", may be useful.
        form = soup.find('form')
        for img in form.find_all('img'):
            # Simply iterating all image objects won't work, because elements and options may be shuffled.
            # Elements order in JSON doesn't change even if shuffle is enabled.
            # Options order can change,
            # but it seems to be always the same in JSON and in HTML form.
            # The current solution (with ids) doesn't depend on element/option order.
            img_obj = None
            option_name = None
            # Option attachment. Guess this one will break first.
            # If a tag is inserted after img.parent,
            # the image will most likely end up in the element's attachment (if it exists)
            option_parent = img.parent.next_sibling
            if option_parent is not None:
                option = option_parent.find(lambda tag: tag.has_attr('data-value'))
                if option is not None:
                    # Option names of a single element are always unique
                    option_name = option['data-value']
            # One of the parents has the element id.
            # The loop should work even if depth of <img> tagis changed.
            for parent in img.parents:
                if parent is form:
                    break
                try:
                    # Image element.
                    if parent.has_attr('data-item-id'):
                        img_obj = images.pop(int(parent['data-item-id']))
                        break
                    # Input element attachment.
                    if parent.has_attr('data-params'):
                        # data-param="%.@.[{element_id},..."
                        dp = parent['data-params']
                        start = dp.index('[') + 1
                        end = dp.index(',', start + 1)
                        element_id = int(dp[start:end])
                        if option_name is not None:
                            img_obj = images.pop((element_id, option_name))
                        else:
                            img_obj = images.pop(element_id)
                        break
                except Exception as e:
                    # Unexpected format change :(
                    # Also may be a KeyError from broken option attachment
                    # if the element itself doesn't have an image.
                    print(f'Cannot find element for image {img["src"]}, error: {e}',
                          file=sys.stderr)
                    break
            if img_obj is not None:
                img_obj.url = img['src']

    def _input_elements(self):
        for page in self.pages:
            for element in page.elements:
                if isinstance(element, InputElement):
                    yield element

    def _iterate_elements(
            self,
            callback: Optional[CallbackType] = None,
            fill_optional=False,
            *,
            do_fill
    ):
        """(optionally) fills and validates the elements.

        Finds pages for submission, skips pages if needed.
        """
        if not self.is_loaded:
            raise FormNotLoaded(self)

        self._invalidate_path()
        page = self.pages[0]
        while page is not None:
            self._select_page(page)
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

                if not elem.is_validated:
                    elem.validate()

            page = page.next_page()
        self._found_full_path = True

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
        last_response = self._first_page

        while True:
            next_page = last_page.next_page()
            if next_page is None:  # Last page
                if update_last_response and last_page is not self.pages[0]:
                    # Load the last page with captcha.
                    # TODO do some more research. Does the captcha refresh?
                    #      (i.e. will it be enough to load the last page only once in Form.load?)
                    # Using the "Back" hack to avoid leaking user input from previous pages
                    # to 3rd party captcha solving services.
                    last_response = self._fetch_page(session, last_page)
                return last_response, last_page, ','.join(history), json.dumps(draft)
            history.append(str(next_page.index))
            if draft[0] is None:
                draft[0] = last_page.draft()
            else:
                draft[0] += last_page.draft()
            last_page = next_page

    def _submit_page(self, session, page, history, draft, *,
                     continue_=True, captcha_response=None, back=False):
        payload = page.payload() if not back else {}

        payload[_ElementNames.FBZX] = self._fbzx
        if continue_ and not back:
            payload['continue'] = 1
        payload[_ElementNames.HISTORY] = history
        if not back:
            payload[_ElementNames.DRAFT] = draft
        if captcha_response is not None:
            payload['g-recaptcha-response'] = captcha_response

        if back:
            payload['back'] = 1

        url = self._response_url(self._first_page.url)
        response = session.post(url, data=payload)
        self._check_resp(response)
        if response.status_code != 200:
            raise RuntimeError('Invalid response code', response)
        return response

    def _fetch_page(self, session, page: Page):
        # The "Back" hack.
        # It's possible to return to any page from the "Submit" page,
        # even if the "Submit" page isn't accessible from the target page.

        return self._submit_page(
            session,
            Page.SUBMIT,
            f'{page.index},{Page.SUBMIT.index}',
            None,
            back=True)

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
        return Form._get_input(soup, _ElementNames.FBZX)

    @staticmethod
    def _get_history(soup):
        return Form._get_input(soup, _ElementNames.HISTORY)

    @staticmethod
    def _get_draft(soup):
        return Form._get_input(soup, _ElementNames.DRAFT)

    @staticmethod
    def _raw_form(soup):
        scripts = soup.find_all('script')
        pattern = re.compile(r'FB_PUBLIC_LOAD_DATA_\s*=\s*(\[.+\])\s*;', re.S)
        for script in scripts:
            if script.string is None:
                continue
            match = pattern.search(script.string)
            if match:
                return json.loads(match.group(1))
        return None
