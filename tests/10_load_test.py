import re
from typing import List, Type

import pytest

from gforms.elements_base import Element
from gforms.elements import Page
from gforms.elements import Comment, Image, Video
from gforms.elements import Short, Paragraph
from gforms.elements import Checkboxes, Dropdown, Radio, Scale
from gforms.elements import CheckboxGrid, RadioGrid
from gforms.elements import Date, DateTime, Time, Duration

from gforms.errors import ClosedForm, ParseError
from gforms.options import ActionOption
from gforms.validators import GridValidator, TextValidator

from .conftest import BaseFormTest


class TestFormLoad:
    def test_invalid_url(self, load_form):
        with pytest.raises(ParseError):
            load_form('https://docs.google.com/forms/d/e/00000000000000000000000000000000000000000000000000000000/viewform')

    def test_closed(self, load_form):
        with pytest.raises(ClosedForm):
            load_form('https://docs.google.com/forms/d/e/1FAIpQLSeq_yONm2qxkvvuY5BI9E3-rDD7RxIQHo9-R_-hy1mZlborKA/viewform')


class TestEmpty(BaseFormTest):
    form_type = 'empty'

    def test_empty(self, form):
        assert form.name == '01_Empty'
        assert form.title == 'Form_title'
        assert form.description == 'Form_description'
        assert len(form.pages) == 1 and len(form.pages[0].elements) == 0


class TestPages(BaseFormTest):
    form_type = 'pages'

    def test_page_count(self, form):
        pages = form.pages
        assert len(pages) == 7

    def test_page_naming(self, form):
        pages = form.pages
        assert pages[0].name is None
        assert pages[1].name == 'Page02'
        assert pages[1].description == 'Page02_descr'

    def test_transitions(self, form):
        pages = form.pages
        assert pages[0].next_page() == pages[1]  # default next page (Action.NEXT)
        assert pages[1].next_page() == pages[0]  # first page (Action.FIRST)
        assert pages[2].next_page() == pages[1]  # page id (go backwards)
        assert pages[3].next_page() == pages[3]  # page id (loop)
        assert pages[4].next_page() == pages[5]  # page id (go forward)
        assert pages[5].next_page() is None  # Action.SUBMIT
        assert pages[6].next_page() is None  # last page


class ElementTest(BaseFormTest):
    expected: List[List[Type[Element]]]

    @pytest.fixture(scope='class')
    def pages(self, form):
        return [page.elements for page in form.pages]

    @pytest.fixture(scope='class')
    def first_page(self, pages):
        return pages[0]

    @pytest.mark.required  # if we cannot parse some elements, most probably other tests will fail
    def test_elements(self, pages):
        types = [[type(elem) for elem in elements] for elements in pages]
        assert types == self.expected


class TestElements(ElementTest):
    form_type = 'elements'
    expected = [[
        Short, Paragraph,
        Radio, Checkboxes, Dropdown, Scale,
        RadioGrid, CheckboxGrid,
        Date, DateTime, Time, Duration,
        Comment, Image, Video
    ]]

    def test_naming(self, first_page):
        for elem in first_page:
            expected_name = type(elem).__name__
            expected_descr = f'{expected_name}_descr'
            assert elem.name == expected_name
            assert elem.description == expected_descr


class TestNonInput(ElementTest):
    form_type = 'non_input'
    expected = [[Comment, Image, Video]]

    def test_video(self, first_page, url):
        video = first_page[2]
        assert video.url() == url.yt_url


class TestTextInput(ElementTest):
    form_type = 'text'
    expected = [[Short, Paragraph]]


class TestRequired(ElementTest):
    form_type = 'required'
    expected = [[Short, Short]]

    def test_required(self, first_page):
        short_required, short_optional = first_page
        assert short_required.required
        assert not short_optional.required


class ChoiceElementTest(ElementTest):
    @staticmethod
    def get_options(elem, expected):
        options = elem.options
        assert len(options) == expected
        for opt in options:
            assert not opt.other
        return options

    @staticmethod
    def assert_has_other(elem):
        assert elem.other_option is not None
        assert elem.other_option.other

    @staticmethod
    def assert_no_other(elem):
        assert elem.other_option is None


class ActChoiceElementTest(ChoiceElementTest):
    @staticmethod
    def assert_has_actions(elem):
        for opt in elem.options:
            assert isinstance(opt, ActionOption)
        if getattr(elem, 'other_option', None) is not None:
            assert isinstance(elem.other_option, ActionOption)

    @staticmethod
    def assert_no_actions(elem):
        for opt in elem.options:
            assert not isinstance(opt, ActionOption)
        if getattr(elem, 'other_option', None) is not None:
            assert not isinstance(elem.other_option, ActionOption)

    @staticmethod
    def assert_ignored_actions(elem):
        for opt in elem.options:
            assert opt.next_page is None
        if getattr(elem, 'other_option', None) is not None:
            assert elem.other_option.next_page is None


class TestRadio(ActChoiceElementTest):
    form_type = 'radio'
    expected = [[Radio, Radio, Radio], [Radio]]

    def test_options(self, pages):
        for page in pages:
            for elem in page:
                opt1, opt2, opt3 = self.get_options(elem, 3)
                assert opt1.value == 'Opt1'
                assert opt2.value == 'Opt2'
                assert opt3.value == 'Opt3'

    def test_other(self, first_page):
        radio, with_other, with_other_and_actions = first_page
        self.assert_no_other(radio)
        self.assert_has_other(with_other)
        self.assert_has_other(with_other_and_actions)

    def test_actions(self, form, first_page):
        _, with_other, with_other_and_actions = first_page
        self.assert_no_actions(with_other)
        self.assert_has_actions(with_other_and_actions)

        opt1, opt2, opt3 = with_other_and_actions.options
        other = with_other_and_actions.other_option
        assert opt1.next_page == form.pages[1]  # default next page
        assert opt2.next_page == form.pages[0]  # Action.FIRST
        assert opt3.next_page == form.pages[1]  # page id (next)
        assert other.next_page == Page.SUBMIT

    def test_ignored_actions(self, pages):
        self.assert_ignored_actions(pages[1][0])


class TestDropdown(ActChoiceElementTest):
    form_type = 'dropdown'
    expected = [[Dropdown, Dropdown], [Dropdown]]

    def test_options(self, pages):
        for page in pages:
            for elem in page:
                opt1, opt2, opt3, opt4 = self.get_options(elem, 4)
                assert opt1.value == 'Opt1'
                assert opt2.value == 'Opt2'
                assert opt3.value == 'Opt3'
                assert opt4.value == 'Opt4'

    def test_actions(self, first_page, form):
        dropdown, with_actions = first_page
        self.assert_no_actions(dropdown)
        self.assert_has_actions(with_actions)

        opt1, opt2, opt3, opt4 = with_actions.options
        assert opt1.next_page == form.pages[1]  # default next page
        assert opt2.next_page == form.pages[0]  # Action.FIRST
        assert opt3.next_page == form.pages[1]  # page id
        assert opt4.next_page == Page.SUBMIT

    def test_ignored_actions(self, pages):
        self.assert_ignored_actions(pages[1][0])


class TestCheckboxes(ChoiceElementTest):
    form_type = 'checkboxes'
    expected = [[Checkboxes, Checkboxes]]

    def test_options(self, first_page):
        for elem in first_page:
            opt1, opt2 = self.get_options(elem, 2)
            assert opt1.value == 'Opt1'
            assert opt2.value == 'Opt2'

    def test_other(self, first_page):
        checkboxes, with_other = first_page
        self.assert_no_other(checkboxes)
        self.assert_has_other(with_other)


class TestScale(ChoiceElementTest):
    form_type = 'scale'
    expected = [[Scale, Scale]]

    def test_options(self, first_page):
        scale5, scale10 = first_page
        assert scale5.low == 'Low'
        assert scale5.high == 'High'

        opts5 = self.get_options(scale5, 5)
        for opt, i in zip(opts5, range(1, 6)):
            assert int(opt.value) == i
        opts10 = self.get_options(scale10, 10)
        for opt, i in zip(opts10, range(1, 11)):
            assert int(opt.value) == i


class TestGrid(ChoiceElementTest):
    form_type = 'grid'
    expected = [[RadioGrid, CheckboxGrid]]

    def test_options(self, first_page):
        for grid in first_page:
            assert len(grid.rows) == len(grid.cols) == 3
            assert [opt.value for opt in grid.cols] == ['C1', 'C2', 'C3']
            assert grid.rows == ['R1', 'R2', 'R3']


class TestDate(ElementTest):
    form_type = 'date'
    expected = [[Date, DateTime, Date, DateTime]]

    def test_year(self, first_page):
        ymd, ymdt, md, mdt = first_page
        assert ymd.has_year
        assert ymdt.has_year
        assert not md.has_year
        assert not mdt.has_year


class TestTime(ElementTest):
    form_type = 'time'
    expected = [[Time, Duration]]


class TestTextValidators(ElementTest):
    form_type = 'text_validation'

    expected = [[Short] * 21, [Paragraph] * 6]
    expected_types = [
        ['NUMBER'] * 11 + ['TEXT'] * 4 + ['LENGTH'] * 2 + ['REGEX'] * 4,
        ['LENGTH'] * 2 + ['REGEX'] * 4,
    ]
    expected_subtypes = [
        [
            'GT', 'GT', 'GE', 'LT', 'LE', 'EQ', 'NE', 'RANGE', 'NOT_RANGE', 'IS_NUMBER', 'IS_INT',
            'CONTAINS', 'NOT_CONTAINS', 'EMAIL', 'URL',
            'MAX_LENGTH', 'MIN_LENGTH',
            'CONTAINS', 'NOT_CONTAINS', 'MATCHES', 'NOT_MATCHES'
        ],
        [
            'MAX_LENGTH', 'MIN_LENGTH',
            'CONTAINS', 'NOT_CONTAINS', 'MATCHES', 'NOT_MATCHES'
        ],
    ]

    @pytest.mark.required
    def test_validator_types(self, pages):
        for page, type_list, subtype_list in zip(pages,
                                                 self.expected_types,
                                                 self.expected_subtypes):
            for element, type_name, subtype_name in zip(page,
                                                        type_list,
                                                        subtype_list):
                validator: TextValidator = element.validator
                assert validator is not None
                type_ = getattr(TextValidator.Type, type_name)
                assert validator.type is type_
                subtype = getattr(type_.subtype_class, subtype_name)
                assert validator.subtype is subtype

    def test_error_msg(self, first_page):
        assert first_page[0].validator.error_msg == 'Error_text'

    def test_number_args(self, first_page):
        for elem in first_page[:7]:  # comparisons
            assert elem.validator.args == [123]
        for elem in first_page[7:9]:  # ranges
            assert elem.validator.args == [123, 456]
        for elem in first_page[9:11]:  # bool
            assert elem.validator.args is None

    def test_text_args(self, first_page):
        for elem in first_page[11:13]:  # should (not) contain a string
            assert elem.validator.args == ['qwe']
        for elem in first_page[13:15]:  # bool
            assert elem.validator.args is None

    def test_length_args(self, first_page):  # paragraphs use the same format
        for elem in first_page[15:17]:  # compare
            assert elem.validator.args == [123]

    def test_regex_args(self, first_page):
        for elem in first_page[17:]:  # pattern
            assert len(elem.validator.args) == 1
            assert isinstance(elem.validator.args[0], re.Pattern)
            assert elem.validator.args[0].pattern == 'qw.rt[a-z]'


class TestGridValidators(ElementTest):
    form_type = 'grid_validation'
    expected = [[RadioGrid, CheckboxGrid]]

    def test_validators(self, first_page):
        r_grid, c_grid = first_page
        assert isinstance(r_grid.validator, GridValidator)
        assert isinstance(c_grid.validator, GridValidator)
        assert r_grid.validator.type == GridValidator.Type.EXCLUSIVE_COLUMNS
