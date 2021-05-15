from abc import ABC, abstractmethod
from typing import Type, List

import pytest

from gforms.elements_base import InputElement, TextInput
from gforms.elements import ElementType, Value
from gforms.elements import Short, Paragraph
from gforms.elements import Checkboxes, Dropdown, Radio, Scale
from gforms.elements import CheckboxGrid, RadioGrid
from gforms.elements import Date, DateTime, Time, Duration

from gforms.errors import IncompatibleType, IncompatibleValue, RequiredElement
from gforms.errors import InvalidText


class ElementTest(ABC):
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
    def elem_type(self) -> Type[InputElement]:
        raise NotImplementedError()

    @property
    @abstractmethod
    def entry_ids(self) -> List[int]:
        raise NotImplementedError()

    @pytest.fixture
    def kwargs(self):
        return {
            'id_': 123456,
            'name': 'Test element',
            'description': 'Element description',
            'type_': self._type_mapping[self.elem_type],
            'entry_ids': self.entry_ids,
        }

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
    def test_invalid_input(self, element, value):
        with pytest.raises(IncompatibleType):
            element.set_value(value)

    def test_empty(self, optional, required):
        with pytest.raises(RequiredElement):
            required.set_value(Value.EMPTY)
        optional.set_value(Value.EMPTY)
        assert optional.payload() == {}


class SingleEntryTest(ElementTest):
    entry_ids = [123]

    @staticmethod
    def check_result(element, value):
        assert element.payload() == {f'entry.{SingleEntryTest.entry_ids[0]}': value}


class TextTest(SingleEntryTest):
    elem_type: Type[TextInput]

    def test_invalid_text_input(self, element):
        with pytest.raises(IncompatibleType):
            element.set_value(['qwe'])

    def test_empty_string(self, optional, required):
        with pytest.raises(RequiredElement):
            required.set_value('')
        optional.set_value('')
        assert optional.payload() == {}

    def test_oneline(self, element):
        element.set_value('Qwe')
        self.check_result(element, ['Qwe'])


class TestShort(TextTest):
    elem_type = Short

    def test_multiline(self, element):
        with pytest.raises(InvalidText):
            element.set_value('Qwe\n')


class TestParagraph(TextTest):
    elem_type = Paragraph

    def test_multiline(self, element):
        element.set_value('Qwe\r\nRty\r\n')
        self.check_result(element, ['Qwe\r\nRty\r\n'])


class ChoiceTest(SingleEntryTest):
    pass


class GridTest(ElementTest):
    pass


class MultipartTest(SingleEntryTest):
    @staticmethod
    def check_result(element, value):
        raise NotImplementedError()


class DateTest(MultipartTest):
    pass


class TimeTest(MultipartTest):
    pass