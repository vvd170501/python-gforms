import pytest

from gforms import Form
from gforms.elements import Page
from gforms.errors import ClosedForm, ParseError

from .util import skip_requests_exceptions


BASIC_FORM_URL = ''


class TestFormLoad:
    def test_invalid_url(self, load_form):
        with pytest.raises(ParseError):
            form = load_form('https://docs.google.com/forms/d/e/00000000000000000000000000000000000000000000000000000000/viewform')

    def test_closed(self, load_form):
        with pytest.raises(ClosedForm):
            form = load_form('https://docs.google.com/forms/d/e/1FAIpQLSeq_yONm2qxkvvuY5BI9E3-rDD7RxIQHo9-R_-hy1mZlborKA/viewform')

    def test_empty(self, load_form, url):
        form = load_form(url.empty)
        assert form.name == '01_Empty'
        assert form.title == 'Form_title'
        assert form.description == 'Form_description'
        assert len(form.pages) == 1 and len(form.pages[0].elements) == 0

    def test_pages(self, load_form, url):
        form = load_form(url.pages)
        pages = form.pages
        assert len(pages) == 7
        assert pages[0].name is None
        assert pages[1].name == 'Page02'
        assert pages[1].description == 'Page02_descr'
        assert pages[0].next_page() == pages[1]  # default next page
        assert pages[1].next_page() == pages[0]  # go backwards
        assert pages[2].next_page() == pages[2]  # loop
        assert pages[3].next_page() == pages[4]  # expicit next page
        assert pages[5].next_page() is None # submit
        assert pages[6].next_page() is None # last page
