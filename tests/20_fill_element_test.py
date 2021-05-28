import re
from abc import ABC, abstractmethod
from datetime import date, datetime, time, timedelta
from typing import Type, List, Tuple, Optional

import pytest

from gforms import Form
from gforms.elements_base import _Action, Element, InputElement, ChoiceInput, ActionChoiceInput, \
    Grid, DateElement, TextInput, ValidatedInput
from gforms.elements import Value, CheckboxGridValue, ElemValue
from gforms.elements import Short, Paragraph
from gforms.elements import Checkboxes, Dropdown, Radio, Scale
from gforms.elements import CheckboxGrid, RadioGrid
from gforms.elements import Date, DateTime, Time, Duration
from gforms.elements import Page

from gforms.errors import ElementTypeError, ElementValueError, RequiredElement, InvalidChoice, \
    EmptyOther, InvalidDuration, RequiredRow, InvalidRowChoice, RowTypeError, DuplicateOther, \
    InfiniteLoop, MisconfiguredElement, SameColumn, InvalidChoiceCount
from gforms.errors import InvalidText
from gforms.options import Option, ActionOption
from gforms.validators import GridValidator, GridTypes, Validator, Subtype, TextValidator, \
    CheckboxValidator, NumberTypes, TextTypes, LengthTypes, RegexTypes, CheckboxTypes

# ChoiceInput elements without "Other" option should raise InvalidChoice for empty strings


INVALID_CHOICE = ''


# ---------- Individual element tests ----------


class ElementTest(ABC):
    elem_type: Type[InputElement]
    entry_ids: List[int]
    allow_strings = False
    allow_lists = False

    @pytest.fixture
    def kwargs(self):
        return {
            'id_': 123456,
            'name': 'Test element',
            'description': 'Element description',
            'type_': self._type_mapping[self.elem_type],
            'entry_ids': self.entry_ids,
        }

    @classmethod
    def _entry_key(cls, index=0, part=None):
        key = f'entry.{cls.entry_ids[index]}'
        if part is not None:
            key += '_' + part
        return key

    @staticmethod
    def get_payload(element, value):
        # NOTE call element.set_value() / validate() / payload() only when testing for exceptions
        # In all other cases, use this method
        element.set_value(value)
        element.validate()
        # NOTE draft() value is never checked (add tests later?)
        _ = element.draft()
        return element.payload()

    @classmethod
    def get_value(cls, payload, *, index=0, part=None):
        return payload[cls._entry_key(index, part)]

    @classmethod
    def extract_value(cls, payload, *, index=0, part=None):
        return payload.pop(cls._entry_key(index, part))

    @classmethod
    def check_empty_value(cls, required, optional, value):
        required.set_value(Value.EMPTY)
        with pytest.raises(RequiredElement):
            required.validate()
        assert cls.get_payload(optional, value) == {}

    _type_mapping = {
        Short: Element.Type.SHORT,
        Paragraph: Element.Type.PARAGRAPH,
        Checkboxes: Element.Type.CHECKBOXES,
        Dropdown: Element.Type.DROPDOWN,
        Radio: Element.Type.RADIO,
        Scale: Element.Type.SCALE,
        CheckboxGrid: Element.Type.GRID, RadioGrid: Element.Type.GRID,
        Date: Element.Type.DATE, DateTime: Element.Type.DATE,
        Time: Element.Type.TIME, Duration: Element.Type.TIME,
    }

    @property
    @abstractmethod
    def elem_type(self):
        raise NotImplementedError()

    @property
    @abstractmethod
    def entry_ids(self) -> List[int]:
        raise NotImplementedError()

    @pytest.fixture
    def optional(self, kwargs):
        kwargs['required'] = False
        return self.elem_type(**kwargs)

    @pytest.fixture
    def required(self, kwargs):
        kwargs['required'] = True
        return self.elem_type(**kwargs)

#     @pytest.fixture(params=[False, True], ids=['optional', 'required'])
#     def element(self, kwargs, request):
#         """Run the test for both required and optional elements"""
#         kwargs['required'] = request.param
#         return self.elem_type(**kwargs)

    # If a test passed for a required element,
    # then it should pass for an optional (=less restricted) element too
    element = required

    def test_invalid_types(self, element, invalid_type):
        with pytest.raises(ElementTypeError):
            element.set_value(invalid_type)

    def test_empty(self, required, optional):
        self.check_empty_value(required, optional, Value.EMPTY)


class SingleEntryTest(ElementTest):
    entry_ids = [123]

    @classmethod
    def check_value(cls, element, value, expected_value):
        payload = cls.get_payload(element, value)
        assert cls.extract_value(payload) == expected_value
        assert payload == {}


class ValidatedTest(ElementTest):
    elem_type: Type[ValidatedInput]

    validator_type: Type[Validator]

    # The following lists' structure:
    #   [(args_for_validator_init, needed_fixture_names, validator_data)]
    # for each item in a list:
    #  - create a test with validator_type(args_for_init)
    #  - request fixtures for the test
    #  - pass validator_data for the test

    # validator_data = (valid_value, invalid_value, expected_exc_type)
    validators: List[Tuple[
        Tuple[Validator.Type, Subtype, Optional[list], Optional[str]],
        List[str], Tuple[ElemValue, ElemValue, Type[Exception]]
    ]]

    # validator_data = any_non_empty_value
    misconfigured: List[Tuple[
        Tuple[Validator.Type, Subtype, Optional[list], Optional[str]],
        List[str], ElemValue
    ]]

    @property
    @abstractmethod
    def validator_type(self):
        raise NotImplementedError()

    @property
    @abstractmethod
    def validators(self):
        raise NotImplementedError()

    @property
    @abstractmethod
    def misconfigured(self):
        raise NotImplementedError()

    @pytest.fixture(autouse=True)
    def empty_validator(self, kwargs):
        kwargs['validator'] = None

    @pytest.fixture
    def validator_data(self, request, kwargs):
        # NOTE this fixture should be used before element
        (val_type, subtype, args, msg), fixtures, ret = request.param
        if isinstance(args, tuple):
            args = list(args)
        elif args is not None:
            args = [args]

        validator = self.validator_type(
            type_=val_type, subtype=subtype, args=args, bad_args=False, error_msg=msg
        )
        kwargs['validator'] = validator  # is applied after empty_validator
        for fixture in fixtures:
            request.getfixturevalue(fixture)
        return ret

    @pytest.fixture
    def val_data(self, request):
        return request.param

    def test_misconfigured(self, validator_data, optional, required):
        # with each validator in self.misconfigured:
        #  - assert MisconfiguredElement is raised on value
        #  - check empty value
        value = validator_data
        optional.set_value(value)
        required.set_value(value)
        with pytest.raises(MisconfiguredElement):
            optional.validate()
        with pytest.raises(MisconfiguredElement):
            required.validate()
        optional.set_value(Value.EMPTY)
        optional.validate()

    def test_validators(self, validator_data, element):
        # for each validator in self.validators:
        #  - check a valid value
        #  - assert the correct exception is raised on invalid value
        valid, invalid, exc = validator_data
        element.set_value(invalid)
        with pytest.raises(exc, match=element.validator.error_msg):
            element.validate()
        element.set_value(valid)
        element.validate()


class TextTest(SingleEntryTest, ValidatedTest):
    elem_type: Type[TextInput]
    allow_strings = True

    validator_type = TextValidator

    def test_empty_string(self, required, optional):
        self.check_empty_value(required, optional, '')

    def test_oneline(self, element):
        value = 'Qwe'
        self.check_value(element, value, [value])


class TestShort(TextTest):
    elem_type = Short

    ptn = re.compile(r'q[a-z]+e')
    validators = [
        ((TextValidator.Type.NUMBER, NumberTypes.GT, 50, 'some_text'),
            [], ('100', '50', InvalidText)),  # test with an error message

        ((TextValidator.Type.NUMBER, NumberTypes.GT, 50, None), [], ('100', '50', InvalidText)),
        ((TextValidator.Type.NUMBER, NumberTypes.GE, 50, None), [], ('50', '0', InvalidText)),
        ((TextValidator.Type.NUMBER, NumberTypes.LT, 50, None), [], ('0', '50', InvalidText)),
        ((TextValidator.Type.NUMBER, NumberTypes.LE, 50, None), [], ('50', '100', InvalidText)),
        ((TextValidator.Type.NUMBER, NumberTypes.EQ, 50, None), [], ('50', '51', InvalidText)),
        ((TextValidator.Type.NUMBER, NumberTypes.NE, 50, None), [], ('51', '50', InvalidText)),
        ((TextValidator.Type.NUMBER, NumberTypes.RANGE, (40, 60), None),
            [], ('50', '100', InvalidText)),
        ((TextValidator.Type.NUMBER, NumberTypes.NOT_RANGE, (40, 60), None),
            [], ('100', '50', InvalidText)),
        ((TextValidator.Type.NUMBER, NumberTypes.IS_NUMBER, None, None),
            [], ('1.23', 'abc', InvalidText)),
        ((TextValidator.Type.NUMBER, NumberTypes.IS_INT, None, None),
            [], ('1', '1.23', InvalidText)),

        ((TextValidator.Type.TEXT, TextTypes.CONTAINS, 'qwe', None),
            [], ('_qwe_', 'abc', InvalidText)),
        ((TextValidator.Type.TEXT, TextTypes.NOT_CONTAINS, 'qwe', None),
            [], ('abc', '_qwe_', InvalidText)),
        ((TextValidator.Type.TEXT, TextTypes.URL, None, None),
            [], ('https://example.com', 'abc', InvalidText)),
        ((TextValidator.Type.TEXT, TextTypes.EMAIL, None, None),
            [], ('user@example.com', 'abc', InvalidText)),

        ((TextValidator.Type.LENGTH, LengthTypes.MAX_LENGTH, 3, None),
            [], ('qwe', 'qwer', InvalidText)),
        ((TextValidator.Type.LENGTH, LengthTypes.MIN_LENGTH, 3, None),
            [], ('qwe', 'qw', InvalidText)),

        # ptn = re.compile(r'q[a-z]+e')
        ((TextValidator.Type.REGEX, RegexTypes.CONTAINS, ptn, None),
            [], ('_qwve_', '_q!e_', InvalidText)),
        ((TextValidator.Type.REGEX, RegexTypes.NOT_CONTAINS, ptn, None),
            [], ('_q!e_', '_qwve_', InvalidText)),
        ((TextValidator.Type.REGEX, RegexTypes.MATCHES, ptn, None),
            [], ('qwve', '_qwve', InvalidText)),
        ((TextValidator.Type.REGEX, RegexTypes.NOT_MATCHES, ptn, None),
            [], ('_qwve', 'qwve', InvalidText)),
    ]

    misconfigured = [
        ((TextValidator.Type.NUMBER, NumberTypes.RANGE, (100, 0), None), [], '50'),
    ]

    def test_multiline(self, element):
        element.set_value('Qwe\n')
        with pytest.raises(InvalidText):
            element.validate()


class TestParagraph(TextTest):
    elem_type = Paragraph

    # Already tested for Short
    validators = {}
    misconfigured = {}

    def test_multiline(self, element):
        value = 'Qwe\r\nRty\r\n'
        self.check_value(element, value, [value])


class ChoiceTest(ElementTest):
    elem_type: Type[ChoiceInput]

    @staticmethod
    @pytest.fixture
    def get_choice(request):
        """returns Option or str (based on param)"""
        need_str = request.param

        def get_choice(option):
            return option.value if need_str else option
        return get_choice

    @staticmethod
    @pytest.fixture
    def get_choice_value(request):
        """returns value of a choice: get_choice_value(get_choice) is always str"""
        used_str = request.param

        def get_choice_value(choice):
            return choice if used_str else choice.value
        return get_choice_value

    # NOTE ChoiceTest subclasses for elements which do not support "Other" values
    # should not have a "test_empty_string" method.
    # Empty strings are checked in test_(.*)invalid_choice methods


class ChoiceTest1D(SingleEntryTest, ChoiceTest):
    elem_type: Type[ChoiceInput]
    allow_strings = True

    @pytest.fixture
    def options(self) -> List[Option]:
        raise NotImplementedError()

    @pytest.fixture(autouse=True)
    def add_options(self, kwargs, options):
        kwargs['options'] = [options]

    def test_choice(self, element, get_choice):
        self.check_value(element, get_choice(element.options[0]), [element.options[0].value])

    def test_invalid_choice(self, element):
        with pytest.raises(InvalidChoice):
            element.set_value(INVALID_CHOICE)


class MayHaveOther(ChoiceTest1D):
    @pytest.fixture
    def other_option(self) -> Option:
        raise NotImplementedError()

    @pytest.fixture(autouse=True)
    def add_other(self, kwargs, other_option):
        kwargs['other_option'] = other_option

    @pytest.fixture
    def no_other(self, kwargs):
        kwargs['other_option'] = None

    @classmethod
    def extract_other(cls, payload):
        value = cls.extract_value(payload)
        assert '__other_option__' in value
        value = [val for val in value if val != '__other_option__']
        if value:
            payload[cls._entry_key()] = value
        return payload.pop(cls._entry_key() + '.other_option_response')

    # noinspection PyMethodOverriding
    def test_empty_string(self, required, optional):
        required.set_value('')
        with pytest.raises(EmptyOther):
            required.validate()
        payload = self.get_payload(optional, '')
        assert payload == {}

    def test_other(self, element, other_option, get_choice):
        other_option.value = 'Other option'
        payload = self.get_payload(element, get_choice(other_option))
        assert self.extract_other(payload) == [other_option.value]
        assert payload == {}

    # when there is no "Other" option, these elements should behave like the base class
    # noinspection PyMethodOverriding
    def test_invalid_choice(self, no_other, element):
        super().test_invalid_choice(element)


class ActionChoiceTest(ChoiceTest1D):
    elem_type: Type[ActionChoiceInput]

    @staticmethod
    def _action_option(value, next_page, other=False):
        opt = ActionOption(value=value, other=other, action=_Action.NEXT)
        opt.next_page = next_page
        return opt

    @pytest.fixture
    def options(self) -> List[Option]:
        return [self._action_option(f'Val{i}', 1000 + i) for i in range(1, 4)]

    def test_transition(self, element, get_choice):
        self.get_payload(element, get_choice(element.options[1]))
        assert element.next_page == element.options[1].next_page


class TestDropdown(ActionChoiceTest):
    elem_type = Dropdown


class TestRadio(MayHaveOther, ActionChoiceTest):
    elem_type = Radio

    @pytest.fixture
    def other_option(self) -> Option:
        return self._action_option('', 2000, other=True)

    def test_other_transition(self, element, get_choice):
        element.other_option.value = 'Other_option'
        self.get_payload(element, get_choice(element.other_option))
        assert element.next_page == element.other_option.next_page


class TestCheckboxes(ValidatedTest, MayHaveOther):
    elem_type = Checkboxes
    allow_lists = True
    # whether or not this class allows list elements to be lists or strings
    allow_list_lists = False
    allow_list_strings = True

    opt_count = 3

    validator_type = CheckboxValidator

    validators = [
        ((CheckboxValidator.Type.DEFAULT, CheckboxTypes.AT_LEAST, 2, None),
            [], (['Opt1', 'Other'], ['Opt1'], InvalidChoiceCount)),  # with "Other" selected

        ((CheckboxValidator.Type.DEFAULT, CheckboxTypes.AT_LEAST, 2, None),
            [], (['Opt1', 'Opt2'], ['Opt1'], InvalidChoiceCount)),
        ((CheckboxValidator.Type.DEFAULT, CheckboxTypes.AT_MOST, 2, None),
            [], (['Opt1', 'Opt2'], ['Opt1', 'Opt2', 'Opt3'], InvalidChoiceCount)),
        ((CheckboxValidator.Type.DEFAULT, CheckboxTypes.EXACTLY, 2, None),
            [], (['Opt1', 'Opt2'], ['Opt1'], InvalidChoiceCount)),

        # Edge case -- need to choose all options, including "Other"
        # Should not raise MisconfiguredElement
        (
            (CheckboxValidator.Type.DEFAULT, CheckboxTypes.AT_LEAST, opt_count + 1, None), [],
            (
                [f'Opt{i+1}' for i in range(opt_count)] + ['Other'],
                ['Opt1'],
                InvalidChoiceCount
            )
        ),
    ]

    misconfigured = [
        ((CheckboxValidator.Type.DEFAULT, CheckboxTypes.EXACTLY, opt_count + 1, None),
            ['no_other'], ['Opt1']),
        ((CheckboxValidator.Type.DEFAULT, CheckboxTypes.AT_LEAST, opt_count + 1, None),
            ['no_other'], ['Opt1']),

        # With "Other"
        ((CheckboxValidator.Type.DEFAULT, CheckboxTypes.EXACTLY, opt_count + 2, None),
            [], ['Opt1']),
    ]

    @pytest.fixture
    def options(self) -> List[Option]:
        return [Option(value=f'Opt{i}', other=False) for i in range(1, self.opt_count + 1)]

    @pytest.fixture
    def other_option(self) -> Option:
        return Option(value='', other=True)

    def test_empty_list(self, required, optional):
        required.set_value([])
        with pytest.raises(RequiredElement):
            required.validate()
        payload = self.get_payload(optional, [])
        assert payload == {}

    def test_list_invalid_type(self, element, invalid_list_type):
        with pytest.raises(ElementTypeError):
            element.set_value([invalid_list_type])

    def test_list_invalid_choice(self, no_other, element):
        with pytest.raises(InvalidChoice):
            element.set_value([element.options[0], INVALID_CHOICE])

    def test_list_with_other(self, element, other_option, get_choice):
        other_option.value = 'Other option'
        choices = [get_choice(opt) for opt in element.options] + [get_choice(other_option)]
        payload = self.get_payload(element, choices)
        assert self.extract_other(payload) == [other_option.value]
        assert self.extract_value(payload) == [opt.value for opt in element.options]
        assert payload == {}

    def test_duplicate_other(self, element):
        with pytest.raises(DuplicateOther):
            element.set_value(['Other1', 'Other2'])

    def test_duplicate_other_opt(self, element):
        with pytest.raises(DuplicateOther):
            element.set_value([element.other_option, element.other_option])


class TestScale(ChoiceTest1D):
    elem_type = Scale

    @pytest.fixture(autouse=True)
    def add_labels(self, kwargs):
        kwargs['low'] = 'Low'
        kwargs['high'] = 'High'

    @pytest.fixture
    def options(self):
        return [Option(value=str(i), other=False) for i in range(1, 11)]

    def test_invalid_int(self, element):
        with pytest.raises(InvalidChoice):
            element.set_value(999)

    def test_int(self, element):
        self.check_value(element, int(element.options[0].value), [element.options[0].value])


class GridTest(ValidatedTest, ChoiceTest):
    elem_type: Type[Grid]
    allow_lists = True
    allow_row_lists = False
    allow_row_strings = True

    validator_type = GridValidator

    row_count = 5
    col_count = 3

    entry_ids = list(range(123, 123 + row_count))

    @pytest.fixture(autouse=True)
    def add_rows(self, kwargs):
        kwargs['rows'] = [f'Row{i}' for i in range(1, self.row_count + 1)]

    @pytest.fixture
    def options(self):
        return [Option(value=f'Col{i}', other=False) for i in range(1, self.col_count + 1)]

    @pytest.fixture(autouse=True)
    def add_options(self, kwargs, options):
        kwargs['options'] = [options] * self.row_count

    def test_row_invalid_type(self, element, invalid_row_type):
        values = [invalid_row_type] * self.row_count
        values[0] = Value.EMPTY
        with pytest.raises(RowTypeError, match='Row2'):
            element.set_value(values)

    def test_invalid_size(self, element):
        values = [element.options[0]] * (self.row_count + 1)
        with pytest.raises(ElementValueError, match=r'Length .* does not match'):
            element.set_value(values)

    def test_empty_row(self, required, optional):
        values = [required.options[0]] * self.row_count
        values[1] = Value.EMPTY
        required.set_value(values)
        with pytest.raises(RequiredRow, match='Row2'):
            required.validate()
        values = [Value.EMPTY] * self.row_count
        values[1] = optional.options[0]
        payload = self.get_payload(optional, values)
        assert self.extract_value(payload, index=1) == [values[1].value]
        assert payload == {}

    def test_row_choice(self, element, get_choice, get_choice_value):
        values = [
            get_choice(element.options[i % self.col_count])
            for i in range(self.row_count)
        ]
        payload = self.get_payload(element, values)
        for i in range(self.row_count):
            assert self.extract_value(payload, index=i) == [get_choice_value(values[i])]
        assert payload == {}

    def test_row_invalid_choice(self, element):
        values = [element.options[0]] * self.row_count
        values[1] = INVALID_CHOICE
        with pytest.raises(InvalidRowChoice, match='Row2'):
            element.set_value(values)


# Run inherited tests and test validation
class TestRadioGrid(GridTest):
    elem_type = RadioGrid

    validators = [(
        (GridValidator.Type.DEFAULT, GridTypes.EXCLUSIVE_COLUMNS, None, None),
        ['wide_grid'],
        (
            [f'Col{i+1}' for i in range(GridTest.row_count)],
            ['Col1'] * GridTest.row_count,
            SameColumn
        )
    )]

    misconfigured = [
        ((GridValidator.Type.DEFAULT, GridTypes.EXCLUSIVE_COLUMNS, None, None),
            [], ['Col1'] * GridTest.row_count),
    ]

    @pytest.fixture
    def wide_grid(self, options):
        # all rows are the same object -> it's sufficient to extend only the first one
        options *= 2
        for i in range(len(options)):
            options[i] = Option(value=f'Col{i+1}', other=False)


class TestCheckboxGrid(GridTest):
    elem_type = CheckboxGrid
    allow_row_lists = True
    allow_row_list_lists = False
    allow_row_list_strings = True

    # Skip validator tests (tested for RagioGrid)
    validators = {}
    misconfigured = {}

    def sample_choice(self, element, get_choice=lambda x: x):
        return [
            [
                get_choice(element.options[i % self.col_count]),
                get_choice(element.options[(i + 1) % self.col_count])
            ]
            for i in range(self.row_count)
        ]

    def test_empty_row_list(self, required, optional):
        values = self.sample_choice(required)[:-1] + [[]]
        required.set_value(values)
        with pytest.raises(RequiredRow):
            required.validate()
        values: CheckboxGridValue = [[]] * self.row_count
        values[1] = optional.options
        payload = self.get_payload(optional, values)
        assert self.extract_value(payload, index=1) == [opt.value for opt in values[1]]
        assert payload == {}

    def test_row_list_invalid_type(self, element, invalid_row_list_type):
        values = self.sample_choice(element)
        values[1][1] = invalid_row_list_type
        with pytest.raises(RowTypeError):
            element.set_value(values)

    def test_row_list_choice(self, element, get_choice, get_choice_value):
        values = self.sample_choice(element, get_choice)
        payload = self.get_payload(element, values)
        for i in range(self.row_count):
            assert self.extract_value(payload, index=i) == \
                   [get_choice_value(choice) for choice in values[i]]
        assert payload == {}

    def test_row_list_invalid_choice(self, element):
        values = self.sample_choice(element)
        values[1][1] = INVALID_CHOICE
        with pytest.raises(InvalidRowChoice):
            element.set_value(values)


class DateTest(SingleEntryTest):
    elem_type: Type[DateElement]

    @pytest.fixture(autouse=True)
    def add_has_year(self, kwargs):
        kwargs['has_year'] = False

    @pytest.fixture
    def with_year(self, kwargs, request):
        if request.param:
            kwargs['has_year'] = True
        return request.param


class TestDateTime(DateTest):
    elem_type = DateTime

    @pytest.mark.parametrize('with_year', [True, False], indirect=True)
    def test_datetime(self, with_year, element):
        value = datetime(2000, 12, 31, 12, 34, 56)
        payload = self.get_payload(element, value)
        if with_year:
            assert self.extract_value(payload, part='year') == value.year
        assert self.extract_value(payload, part='month') == value.month
        assert self.extract_value(payload, part='day') == value.day
        assert self.extract_value(payload, part='hour') == value.hour
        assert self.extract_value(payload, part='minute') == value.minute
        assert payload == {}


class TestDate(DateTest):
    elem_type = Date

    @pytest.mark.parametrize('with_year', [True, False], indirect=True)
    def test_date(self, with_year, element):
        value = date(2000, 12, 31)
        payload = self.get_payload(element, value)
        if with_year:
            assert self.extract_value(payload, part='year') == value.year
        assert self.extract_value(payload, part='month') == value.month
        assert self.extract_value(payload, part='day') == value.day
        assert payload == {}


class TestTime(SingleEntryTest):
    elem_type = Time

    def test_time(self, element):
        value = time(hour=12, minute=34, second=56)
        payload = self.get_payload(element, value)
        assert self.extract_value(payload, part='hour') == value.hour
        assert self.extract_value(payload, part='minute') == value.minute
        assert payload == {}


class TestDuration(SingleEntryTest):
    elem_type = Duration

    def test_duration(self, element):
        h, m, s = 12, 34, 56
        payload = self.get_payload(element,
                                   timedelta(hours=h, minutes=m, seconds=s))
        assert self.extract_value(payload, part='hour') == h
        assert self.extract_value(payload, part='minute') == m
        assert self.extract_value(payload, part='second') == s
        assert payload == {}

    @pytest.mark.parametrize('duration', [timedelta(seconds=73*3600), timedelta(seconds=-1)])
    def test_invalid_duration(self, element, duration):
        element.set_value(duration)
        with pytest.raises(InvalidDuration):
            element.validate()


# ---------- Page transition tests ----------


class TestTransitions:
    @staticmethod
    def _page(id_):
        return Page(id_=id_,
                    name='Test page', description=None, type_=Element.Type.PAGE,
                    prev_action=_Action.NEXT)

    @staticmethod
    def _dropdown(id_, entry_id, options):
        return Dropdown(
            id_=id_,
            name='Test dropdown', description=None, type_=Element.Type.DROPDOWN,
            entry_ids=[entry_id],  # actually doesn't matter
            required=False,
            options=[options]
        )

    @staticmethod
    @pytest.fixture
    def form():
        """
        A form with 3 pages, each has 2 dropdowns.
        Each dropdown has three options:
            - "Go to the first page"
            - "Go to the second page"
            - "Go to submit page"
        """
        pages = [Page.first()] + [TestTransitions._page(100000 + 1000 * i) for i in range(2)]
        for page in pages:
            for i in range(2):
                options = [
                    ActionOption(value=f'First', other=False, action=_Action.FIRST),
                    ActionOption(value=f'Second', other=False, action=pages[1].id),
                    ActionOption(value=f'Submit', other=False, action=_Action.SUBMIT),
                ]
                page.append(TestTransitions._dropdown(id_=page.id + 100 * i,  # just unique ids
                                                      entry_id=page.id + 100 * i + 10,
                                                      options=options))
        form = Form('')
        form.pages = pages
        form._resolve_actions()
        form._is_loaded = True
        return form

    def test_single_element(self, form):
        page = form.pages[0]
        page.elements[0].set_value('First')
        assert page.next_page() == form.pages[0]

    def test_multiple_elements(self, form):
        page = form.pages[0]
        page.elements[0].set_value('First')
        page.elements[0].set_value('Submit')
        assert page.next_page() == Page.SUBMIT

    def test_ignored_transitions(self, form):
        page = form.pages[-1]
        page.elements[0].set_value('First')
        assert page.next_page() is None

    def test_infinite_loop(self, form: Form):
        def callback(elem, page_index, elem_index):
            if page_index == 0 and elem_index == 0:
                return 'First'
            return Value.EMPTY

        with pytest.raises(InfiniteLoop):
            form.fill(callback, fill_optional=False)
