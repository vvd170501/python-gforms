from abc import ABC, abstractmethod

import pytest

from .conftest import RealFormTest


# NOTE actual submission results aren't checked
class TestSubmitEmpty(RealFormTest):
    form_type = 'empty'

    def test_submit(self, form, session):
        # An empty single-page form doesn't need to be validated
        form.submit(session)


class TestSubmitShortLink(RealFormTest):
    form_type = 'empty_short'  # A short link for the same empty form

    def test_submit(self, form, session):
        form.submit(session)


class WithEmulation(RealFormTest, ABC):
    @staticmethod
    @abstractmethod
    def _callback(elem, i, j):
        raise NotImplementedError()

    @pytest.fixture(scope='class', autouse=True)
    def fill_form(self, form):
        # Here the form is filled in class scope => no need to use mutable_form
        form.fill(self._callback)

    def test_submit_normal(self, form, session):
        form.submit(session)

    def test_submit_emulated(self, form, session):
        # TODO check submission result? (export responses to a spreadsheet, use gspread)
        form.submit(session, emulate_history=True)


class TestSubmitMultipage(WithEmulation):
    """The form contains two pages, on each of them there is a short text input."""
    form_type = 'submit_multipage'

    @staticmethod
    def _callback(elem, i, j):
        return 'Sample text'


class TestSubmitEmail(WithEmulation):
    """The form contains two empty pages and requires an e-mail.

    The response receipt may be requested by user."""
    form_type = 'submit_email'

    @staticmethod
    def _callback(elem, i, j):
        return 'qwerty@example.com'

    def test_no_handler(self, form, session):
        with pytest.raises(ValueError, match='handler is missing'):
            form.submit(session, need_receipt=True)


# TODO test if exceptions are raised on signin redirect
