from abc import ABC, abstractmethod
from datetime import date, datetime, time, timedelta
from typing import Type, List, Union

import pytest

from gforms.elements_base import InputElement, TextInput, DateElement, ChoiceInput, Grid, \
    ActionChoiceInput, Action
from gforms.elements import ElementType, Value
from gforms.elements import Short, Paragraph
from gforms.elements import Checkboxes, Dropdown, Radio, Scale
from gforms.elements import CheckboxGrid, RadioGrid
from gforms.elements import Date, DateTime, Time, Duration

from gforms.errors import ElementTypeError, ElementValueError, RequiredElement, InvalidChoice, \
    EmptyOther
from gforms.errors import InvalidText
from gforms.options import Option, ActionOption


class ElementTest(ABC):
    elem_type: Type[InputElement]
    entry_ids: List[int]

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

    @classmethod
    def get_value(cls, payload, index=0, part=None):
        return payload[cls._entry_key(index, part)]

    @classmethod
    def extract_value(cls, payload, index=0, part=None):
        return payload.pop(cls._entry_key(index, part))

    @staticmethod
    def check_empty_value(required, optional, value):
        required.set_value(Value.EMPTY)
        with pytest.raises(RequiredElement):
            required.validate()
        optional.set_value(value)
        optional.validate()
        assert optional.payload() == {}

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

    @pytest.mark.parametrize("value", [{}, b'', None, False, True])
    def test_invalid_types(self, element, value):
        with pytest.raises(ElementTypeError):
            element.set_value(value)

    def test_empty(self, required, optional):
        self.check_empty_value(required, optional, Value.EMPTY)


class SingleEntryTest(ElementTest):
    entry_ids = [123]
    @classmethod
    def check_value(cls, element, value, expected_value):
        element.set_value(value)
        payload = element.payload()
        assert cls.extract_value(payload) == expected_value
        assert payload == {}


class AcceptsStr(ElementTest):
    def test_empty_string(self, required, optional):
        self.check_empty_value(required, optional, '')


class TextTest(SingleEntryTest, AcceptsStr):
    elem_type: Type[TextInput]

    def test_not_a_str(self, element):
        with pytest.raises(ElementTypeError):
            element.set_value(['qwe'])

    def test_oneline(self, element):
        value = 'Qwe'
        self.check_value(element, value, [value])


class TestShort(TextTest):
    elem_type = Short

    def test_multiline(self, element):
        with pytest.raises(InvalidText):
            element.set_value('Qwe\n')


class TestParagraph(TextTest):
    elem_type = Paragraph

    def test_multiline(self, element):
        value = 'Qwe\r\nRty\r\n'
        self.check_value(element, value, [value])


class ChoiceTest1D(SingleEntryTest, AcceptsStr):
    elem_type: Type[ChoiceInput]

    @pytest.fixture
    def options(self) -> List[Option]:
        raise NotImplementedError()

    @pytest.fixture(autouse=True)
    def add_options(self, kwargs, options):
        kwargs['options'] = [options]

    def test_option(self, element, options):
        self.check_value(element, options[0], [options[0].value])

    def test_string(self, element, options):
        self.check_value(element, options[0].value, [options[0].value])


class DisallowOther(ChoiceTest1D):
    def test_invalid_string(self, element):
        with pytest.raises(InvalidChoice):
            element.set_value('Not an option')


class SingleChoice1D(ChoiceTest1D):
    def test_disallow_list(self, element):
        with pytest.raises(ElementTypeError):
            element.set_value([])


class ChoiceWithOther(ChoiceTest1D):
    @pytest.fixture
    def other_option(self) -> Option:
        raise NotImplementedError()

    @pytest.fixture(autouse=True)
    def add_other(self, kwargs, other_option):
        kwargs['other_option'] = other_option

    @pytest.fixture
    def no_other(self, kwargs):
        kwargs['other_option'] = None

    def test_empty_other(self, required, optional):
        required.set_value('')
        with pytest.raises(EmptyOther):
            required.validate()

class ActionChoiceTest(SingleChoice1D):
    elem_type: Type[ActionChoiceInput]

    @staticmethod
    def _action_option(value, next_page, other=False):
        opt = ActionOption(value=value, other=other, action=Action.NEXT)
        opt.next_page = next_page
        return opt

    @pytest.fixture
    def options(self) -> List[Option]:
        return [self._action_option(f'Val{i}', 1000 + i) for i in range(3)]


class TestCheckboxes(ChoiceWithOther):
    elem_type = Checkboxes

    @pytest.fixture
    def options(self) -> List[Option]:
        return [Option(value=f'Opt{i}', other=False) for i in range(1, 4)]

    @pytest.fixture
    def other_option(self) -> Option:
        return Option(value='', other=True)
    # TODO


class TestDropdown(ActionChoiceTest, DisallowOther):
    elem_type = Dropdown
    # TODO


class TestRadio(ActionChoiceTest, ChoiceWithOther):
    elem_type = Radio

    @pytest.fixture
    def other_option(self) -> Option:
        return self._action_option('', 2000)
    # TODO


class TestScale(SingleChoice1D, DisallowOther):
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

    def test_int(self, element, options):
        self.check_value(element, int(options[0].value), options[0].value)


class GridTest(ElementTest):
    row_count = 5
    col_count = 3

    entry_ids = list(range(123, 123 + row_count))
    elem_type: Type[Grid]

    @pytest.fixture(autouse=True)
    def add_rows(self, kwargs):
        kwargs['rows'] = [f'Row{i}' for i in range(1, self.row_count + 1)]

    @pytest.fixture(autouse=True)
    def add_options(self, kwargs):
        opt_row = [f'Col{i}' for i in range(1, self.col_count + 1)]
        kwargs['options'] = opt_row * self.row_count


class TestRadioGrid(GridTest):
    elem_type = RadioGrid
    # TODO


class TestCheckboxGrid(GridTest):
    elem_type = CheckboxGrid
    # TODO


class DateTest(SingleEntryTest):
    elem_type: Type[DateElement]

    @pytest.fixture(autouse=True)
    def add_has_year(self, kwargs):
        kwargs['has_year'] = False

    @pytest.fixture
    def with_year(self, kwargs):
        kwargs['has_year'] = True


class TestDateTime(DateTest):
    elem_type = DateTime
    # TODO


class TestDate(DateTest):
    elem_type = Date
    # TODO


class TestTime(SingleEntryTest):
    elem_type = Time
    # TODO


class TestDuration(SingleEntryTest):
    elem_type = Duration
    # TODO
