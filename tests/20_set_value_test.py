from abc import ABC, abstractmethod
from datetime import date, datetime, time, timedelta
from typing import Type, List

import pytest

from gforms.elements_base import InputElement, TextInput, DateElement, ChoiceInput, Grid, \
    ActionChoiceInput, Action
from gforms.elements import ElementType, Value, CheckboxGridValue
from gforms.elements import Short, Paragraph
from gforms.elements import Checkboxes, Dropdown, Radio, Scale
from gforms.elements import CheckboxGrid, RadioGrid
from gforms.elements import Date, DateTime, Time, Duration

from gforms.errors import ElementTypeError, ElementValueError, RequiredElement, InvalidChoice, \
    EmptyOther, InvalidDuration, RequiredRow, InvalidRowChoice, RowTypeError, DuplicateOther
from gforms.errors import InvalidText
from gforms.options import Option, ActionOption


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
        Short: ElementType.SHORT,
        Paragraph: ElementType.PARAGRAPH,
        Checkboxes: ElementType.CHECKBOXES,
        Dropdown: ElementType.DROPDOWN,
        Radio: ElementType.RADIO,
        Scale: ElementType.SCALE,
        CheckboxGrid: ElementType.GRID, RadioGrid: ElementType.GRID,
        Date: ElementType.DATE, DateTime: ElementType.DATE,
        Time: ElementType.TIME, Duration: ElementType.TIME,
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

    @pytest.fixture(params=[False, True], ids=['optional', 'required'])
    def element(self, kwargs, request):
        kwargs['required'] = request.param
        return self.elem_type(**kwargs)

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


class TextTest(SingleEntryTest):
    elem_type: Type[TextInput]
    allow_strings = True

    def test_empty_string(self, required, optional):
        self.check_empty_value(required, optional, '')

    def test_oneline(self, element):
        value = 'Qwe'
        self.check_value(element, value, [value])


class TestShort(TextTest):
    elem_type = Short

    def test_multiline(self, element):
        element.set_value('Qwe\n')
        with pytest.raises(InvalidText):
            element.validate()


class TestParagraph(TextTest):
    elem_type = Paragraph

    def test_multiline(self, element):
        value = 'Qwe\r\nRty\r\n'
        self.check_value(element, value, [value])


class ChoiceTest(ElementTest):
    elem_type: Type[ChoiceInput]

    @pytest.fixture
    def get_choice(self, request):
        """returns Option or str (based on param)"""
        need_str = request.param

        def get_choice(option):
            return option.value if need_str else option
        return get_choice

    @pytest.fixture
    def get_choice_value(self, request):
        """returns value of a choice: get_choice_value(get_choice) is always str"""
        used_str = request.param

        def get_choice_value(choice):
            return choice if used_str else choice.value
        return get_choice_value


class ChoiceTest1D(SingleEntryTest, ChoiceTest):
    elem_type: Type[ChoiceInput]
    allow_strings = True

    @pytest.fixture
    def options(self) -> List[Option]:
        raise NotImplementedError()

    @pytest.fixture(autouse=True)
    def add_options(self, kwargs, options):
        kwargs['options'] = [options]

    def test_empty_string(self, element):
        with pytest.raises(InvalidChoice):
            element.set_value('')

    def test_choice(self, element, get_choice):
        self.check_value(element, get_choice(element.options[0]), [element.options[0].value])


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

    def test_no_other(self, no_other, element):
        with pytest.raises(InvalidChoice):
            element.set_value('Not an option')


###################################### TODO #######################################


class ActionChoiceTest(ChoiceTest1D):
    elem_type: Type[ActionChoiceInput]

    @staticmethod
    def _action_option(value, next_page, other=False):
        opt = ActionOption(value=value, other=other, action=Action.NEXT)
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


class TestCheckboxes(MayHaveOther):
    elem_type = Checkboxes
    allow_lists = True
    allow_choice_lists = False
    allow_choice_strings = True

    @pytest.fixture
    def options(self) -> List[Option]:
        return [Option(value=f'Opt{i}', other=False) for i in range(1, 4)]

    @pytest.fixture
    def other_option(self) -> Option:
        return Option(value='', other=True)

    def test_empty_list(self, required, optional):
        required.set_value([])
        with pytest.raises(RequiredElement):
            required.validate()
        payload = self.get_payload(optional, [])
        assert payload == {}

    def test_invalid_choice_type(self, element, invalid_choice_type):
        with pytest.raises(ElementTypeError):
            element.set_value([invalid_choice_type])

    def test_with_invalid_choice(self, no_other, element):
        with pytest.raises(InvalidChoice):
            element.set_value([element.options[0], 'Not an option'])

    def test_choice_with_other(self, element, other_option, get_choice):
        other_option.value = 'Other option'
        choices = [get_choice(opt) for opt in element.options] + [get_choice(other_option)]
        payload = self.get_payload(element, choices)
        assert self.extract_other(payload) == [other_option.value]
        assert self.extract_value(payload) == [opt.value for opt in element.options]
        assert payload == {}

    def test_duplicate_other(self, element):
        with pytest.raises(DuplicateOther):
            element.set_value(['Other1', 'Other2'])


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


class GridTest(ChoiceTest):
    elem_type: Type[Grid]
    allow_lists = True
    allow_entry_lists = False
    allow_entry_strings = True

    row_count = 5
    col_count = 3

    entry_ids = list(range(123, 123 + row_count))

    @pytest.fixture(autouse=True)
    def add_rows(self, kwargs):
        kwargs['rows'] = [f'Row{i}' for i in range(1, self.row_count + 1)]

    @pytest.fixture(autouse=True)
    def add_options(self, kwargs):
        opt_row = [Option(value=f'Col{i}', other=False) for i in range(1, self.col_count + 1)]
        kwargs['options'] = [opt_row] * self.row_count

    def test_invalid_row_type(self, element, invalid_entry_type):
        values = [invalid_entry_type] * self.row_count
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

    def test_choice(self, element, get_choice, get_choice_value):
        values = [
            get_choice(element.options[i % self.col_count])
            for i in range(self.row_count)
        ]
        payload = self.get_payload(element, values)
        for i in range(self.row_count):
            assert self.extract_value(payload, index=i) == [get_choice_value(values[i])]
        assert payload == {}

    def test_invalid_row_choice(self, element):
        values = [element.options[0]] * self.row_count
        values[1] = 'Not an option;'
        with pytest.raises(InvalidRowChoice, match='Row2'):
            element.set_value(values)


class TestRadioGrid(GridTest):
    elem_type = RadioGrid


class TestCheckboxGrid(GridTest):
    elem_type = CheckboxGrid
    allow_entry_lists = True
    allow_choice_lists = False
    allow_choice_strings = True

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

    def test_invalid_choice_type(self, element, invalid_choice_type):
        values = self.sample_choice(element)
        values[1][1] = invalid_choice_type
        with pytest.raises(RowTypeError):
            element.set_value(values)

    def test_choices(self, element, get_choice, get_choice_value):
        values = self.sample_choice(element, get_choice)
        payload = self.get_payload(element, values)
        for i in range(self.row_count):
            assert self.extract_value(payload, index=i) == \
                   [get_choice_value(choice) for choice in values[i]]
        assert payload == {}

    def test_invalid_row_choices(self, element):
        values = self.sample_choice(element)
        values[1][1] = 'Not an option'
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
