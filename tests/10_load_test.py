import pytest

from gforms import Form
from gforms.elements import Value
from gforms.elements import Page
from gforms.elements import Comment, Image, Video
from gforms.elements import Short, Paragraph
from gforms.elements import Checkboxes, Dropdown, Grid, Radio, Scale
from gforms.errors import ClosedForm, ParseError
from gforms.options import ActionOption, Option

from .util import BaseFormTest


BASIC_FORM_URL = ''


class TestFormLoad:
    def test(self, load_form):
        with pytest.raises(ParseError):
            form = load_form('https://docs.google.com/forms/d/e/00000000000000000000000000000000000000000000000000000000/viewform')

    def test_closed(self, load_form):
        with pytest.raises(ClosedForm):
            form = load_form('https://docs.google.com/forms/d/e/1FAIpQLSeq_yONm2qxkvvuY5BI9E3-rDD7RxIQHo9-R_-hy1mZlborKA/viewform')


class TestEmpty(BaseFormTest):
    form_type = 'empty'

    def test_empty(self, form):
        assert form.name == '01_Empty'
        assert form.title == 'Form_title'
        assert form.description == 'Form_description'
        assert len(form.pages) == 1 and len(form.pages[0].elements) == 0


def check_with_descr(elem, name=None):
    """Assert that element's name and description were parsed correctly"""
    if name is None:
        name = type(elem).__name__
    assert elem.name == name and elem.description == f'{name}_descr'


class TestPages(BaseFormTest):
    form_type = 'pages'

    def test_pages(self, form):
        pages = form.pages
        assert len(pages) == 7
        assert pages[0].name is None
        check_with_descr(pages[1], 'Page02')

        assert pages[0].next_page() == pages[1]  # default next page
        assert pages[1].next_page() == pages[0]  # go backwards
        assert pages[2].next_page() == pages[2]  # loop
        assert pages[3].next_page() == pages[4]  # expiicit next page
        assert pages[5].next_page() is None # submit
        assert pages[6].next_page() is None # last page


def get_elements(form, expected, page=0):
    """Check number of elements on the selected page and return these elements"""
    elements = form.pages[page].elements
    assert len(elements) == expected
    return elements


class TestNonInput(BaseFormTest):
    form_type = 'non_input'

    def test_elements(self, form, url):
        comment, image, video = get_elements(form, 3)
        assert isinstance(comment, Comment)
        assert isinstance(image, Image)
        assert isinstance(video, Video)
        check_with_descr(comment)
        check_with_descr(image)
        check_with_descr(video)
        assert video.url() == url.yt_url


class TestTextInput(BaseFormTest):
    form_type = 'text'

    def test_text(self, form):
        short, paragraph = get_elements(form, 2)
        assert isinstance(short, Short)
        assert isinstance(paragraph, Paragraph)
        check_with_descr(short)
        check_with_descr(paragraph)


# assuming that name and description are correctly parsed for all further types


class TestRequire(BaseFormTest):
    form_type = 'required'

    def test_required(self, form):
        short_required, short_optional = get_elements(form, 2)
        assert short_required.required
        assert not short_optional.required


def get_options(elem, expected):
    options = elem.options
    assert len(options) == expected
    return options


def assert_has_other(elem):
    assert elem.other_option is not None
    assert elem.other_option.other


class TestRadio(BaseFormTest):
    form_type = 'radio'

    def test_options(self, form):
        elements = get_elements(form, 3)
        assert isinstance(elements[0], Radio)  # all other elements are Radio
        for elem in elements:
            opt1, opt2 = get_options(elem, 2)
            assert opt1.value == 'Opt1'
            assert opt2.value == 'Opt2'

    def test_other(self, form):
        radio, with_other, _ = get_elements(form, 3)
        assert all(not opt.other for opt in radio.options)
        assert radio.other_option is None

        assert all(not opt.other for opt in with_other.options)
        assert_has_other(with_other)

    def test_actions(self, form):
        _, with_other, with_other_and_actions = get_elements(form, 3)
        for opt in with_other.options:
            assert not isinstance(opt, ActionOption)
        assert not isinstance(with_other.other_option, ActionOption)

        opt1, opt2, other = *with_other_and_actions.options, with_other_and_actions.other_option
        assert isinstance(opt1, ActionOption)
        assert isinstance(opt2, ActionOption)
        assert isinstance(other, ActionOption)
        assert opt1.next_page == form.pages[1]  # default next page
        assert opt2.next_page == form.pages[0]  # loop (explicit page)
        assert other.next_page == Page.SUBMIT()

    def test_actions_ignored(self, form):
        with_other_and_actions = get_elements(form, 1, page=1)[0]
        assert all (opt.next_page is None for opt in with_other_and_actions.options)
        assert with_other_and_actions.other_option.next_page is None


class TestDropdown(BaseFormTest):
    form_type = 'dropdown'

    # Maybe it's better to create a test class for ActChoiceInputElement and another one for "Other" options
    def test_options(self, form):
        elements = get_elements(form, 2)
        assert isinstance(elements[0], Dropdown)
        for elem in elements:
            opt1, opt2 = get_options(elem, 2)
            assert opt1.value == 'Opt1'
            assert opt2.value == 'Opt2'

    def test_actions(self, form):
        dropdown, with_actions = get_elements(form, 2)
        for opt in dropdown.options:
            assert not isinstance(opt, ActionOption)

        opt1, opt2 = with_actions.options
        assert isinstance(opt1, ActionOption)
        assert isinstance(opt2, ActionOption)
        assert opt1.next_page == form.pages[1]  # default next page
        assert opt2.next_page == form.pages[0]  # loop (explicit page)

    def test_actions_ignored(self, form):
        dropdown = get_elements(form, 1, page=1)[0]
        assert all (opt.next_page is None for opt in dropdown.options)


class TestCheckboxes(BaseFormTest):
    form_type = 'checkboxes'

    def test_options(self, form):
        elements = get_elements(form, 2)
        assert isinstance(elements[0], Checkboxes)
        for elem in elements:
            opt1, opt2 = get_options(elem, 2)
            assert opt1.value == 'Opt1'
            assert not opt1.other
            assert opt2.value == 'Opt2'
            assert not opt2.other

    def test_other(self, form):
        checkboxes, with_other = get_elements(form, 2)
        assert checkboxes.other_option is None
        assert_has_other(with_other)


class TestScale(BaseFormTest):
    form_type = 'scale'

    def test_options(self, form):
        scale5, scale10 = get_elements(form, 2)
        assert isinstance(scale5, Scale)
        assert scale5.low == 'Low'
        assert scale5.high == 'High'
        opts5 = get_options(scale5, 5)
        assert all(int(opt.value) == i for opt, i in zip(opts5, range(1, 6)))
        opts10 = get_options(scale10, 10)
        assert all(int(opt.value) == i for opt, i in zip(opts10, range(1, 11)))


class TestGrid(BaseFormTest):
    form_type = 'grid'

    def test_radio_grid(self, form):
        grid, _ = get_elements(form, 2)
        assert isinstance(grid, Grid)
        assert not grid.multichoice
        assert len(grid.rows) == len(grid.cols) == 3
        assert [opt.value for opt in grid.cols] == ['C1', 'C2', 'C3']
        assert grid.rows == ['R1', 'R2', 'R3']

    def test_checkbox_grid(self, form):
        _, grid = get_elements(form, 2)
        assert grid.multichoice


class TestDate(BaseFormTest):
    pass


class TestTime(BaseFormTest):
    pass
