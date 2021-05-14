from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from enum import Enum, auto
from typing import Dict, List, Literal, Union, cast

from .errors import DuplicateOther, EmptyOther, InvalidChoice, MultipleValues, \
                    RequiredElement, invalid_type
from .options import ActionOption, Option, parse as parse_option
from .util import add_indent


class Value(Enum):
    DEFAULT = auto()
    EMPTY = auto()


EmptyValue = Literal[Value.EMPTY]
TextValue = str
ChoiceValue = Union[str, Option]
MultiChoiceValue = Union[ChoiceValue, List[ChoiceValue]]

GridChoiceValue = List[
    Union[ChoiceValue, EmptyValue]
]

GridMultiChoiceValue = List[
    Union[MultiChoiceValue, EmptyValue]
]

GridValue = Union[GridChoiceValue, GridMultiChoiceValue]


class ElementType(Enum):
    # NOTE File upload element is not implemented
    # TODO add custom validation for short text / paragraph / checkboxes / grid
    SHORT = 0
    PARAGRAPH = 1
    RADIO = 2
    DROPDOWN = 3
    CHECKBOXES = 4
    SCALE = 5
    COMMENT = 6
    GRID = 7
    PAGE = 8
    DATE = 9
    TIME = 10
    IMAGE = 11
    VIDEO = 12


class Action:
    FIRST = -1
    NEXT = -2
    SUBMIT = -3


class Element:
    class Index:
        ID = 0
        NAME = 1
        DESCRIPTION = 2
        TYPE = 3

    @classmethod
    def parse(cls, elem):
        return cls(**cls._parse(elem))

    @classmethod
    def _parse(cls, elem):
        return {
            'id_': elem[cls.Index.ID],
            'name': elem[cls.Index.NAME],
            'description': elem[cls.Index.DESCRIPTION],  # may be None
            'type_': ElementType(elem[cls.Index.TYPE]),
        }

    def __init__(self, *, id_, name, description, type_):
        self.id = id_
        self.name = name
        self.description = description
        self.type = type_

    def to_str(self, indent=0, **kwargs):
        s = f'{self._type_str()}'
        if self.name:
            s = f'{s}: {self.name}'
        if self.description:
            s = f'{s}\n{self.description}'
        return s

    def _type_str(self):
        return type(self).__name__


class InputElement(Element, ABC):
    class Index(Element.Index):
        ENTRIES = 4
        ENTRY_ID = 0
        OPTIONS = 1
        REQUIRED = 2

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        entries = cls._get_entries(elem)
        res.update({
            'entry_ids': [e[cls.Index.ENTRY_ID] for e in entries],
            'required': entries[0][cls.Index.REQUIRED],  # same for all entries
        })
        return res

    def __init__(self, *, entry_ids, required, **kwargs):
        super().__init__(**kwargs)
        self._entry_ids = entry_ids
        self.required = required
        self._values: List[List[str]] = [[] for _ in self._entry_ids]

    @abstractmethod
    def set_value(self, value):
        raise NotImplementedError()

    def to_str(self, indent=0, include_answer=False):
        s = f'{self._type_str()}: {self.name}'
        if self.required:
            s += '*'
        if self.description:
            s = f'{s}\n{self.description}'
        hints = self._hints(indent)
        if hints:
            s = '\n'.join([s] + hints)
        if include_answer:
            s = '\n'.join([s] + self._answer())
        return s

    def payload(self) -> Dict[str, List[str]]:
        payload = {}
        for entry_id, value in zip(self._entry_ids, self._values):
            if value:
                payload[self._submit_id(entry_id)] = value[:]
        return payload

    @staticmethod
    def _submit_id(entry_id):
        return f'entry.{entry_id}'

    @staticmethod
    def _get_entries(elem):
        return elem[InputElement.Index.ENTRIES]

    def _set_values(self, values: List[Union[List[str], EmptyValue]]):
        values = values[:]
        for i, entry_values in enumerate(values):
            if entry_values is Value.EMPTY:
                values[i] = []

        self._values = values  # type: ignore
        self._validate()

    def _validate(self):
        if self.required:
            for i, value in enumerate(self._values):
                if not value:
                    raise RequiredElement(self, i)

    def _hints(self, indent=0):
        """Input hints (options / values). Returned strings should be already indented"""
        return []

    def _answer(self) -> List[str]:
        return [f'> {self._entry_answer(i)}' for i in range(len(self._entry_ids))]

    def _entry_answer(self, i) -> str:
        entry_val = self._values[i]
        if not entry_val:
            return 'EMPTY'
        return ', '.join(f'"{value}"' for value in entry_val)


class SingleInput(InputElement, ABC):
    """InputElement with 1 entry"""

    def _set_value(self, value: Union[List[str], EmptyValue]):
        self._set_values([value])

    @property
    def _value(self):
        return self._values[0]

    @property
    def _entry_id(self):
        return self._entry_ids[0]

    def _part_id(self, name):
        return f'{self._submit_id(self._entry_id)}_{name}'

    @staticmethod
    def _get_value(elem):
        return InputElement._get_entries(elem)[0]


class ChoiceInput(InputElement, ABC):
    # basically a CheckboxGrid

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        options = [
            [
                parse_option(opt) for opt in entry[cls.Index.OPTIONS]
            ] for entry in cls._get_entries(elem)
        ]
        res.update({
            'options': options,
        })
        return res

    def __init__(self, *, options: List[List[Option]], **kwargs):
        super().__init__(**kwargs)
        self._options = options

    @property
    @abstractmethod
    def options(self):
        raise NotImplementedError()

    def _set_choices(self, choices: List[Union[List[ChoiceValue], EmptyValue]]):
        new_choices: List[Union[List[str], EmptyValue]] = [[] for _ in choices]
        for i, entry_choices in enumerate(choices):
            if entry_choices is Value.EMPTY:
                continue
            for choice in cast(List[ChoiceValue], entry_choices):
                self._add_choice(
                    new_choices[i],
                    self._find_option(choice, i)
                )
        self._set_values(new_choices)

    @abstractmethod
    def _hints(self, indent=0):
        raise NotImplementedError()

    def _find_option(self, value: ChoiceValue, i):
        if isinstance(value, Option):
            # assuming value was chosen from self.options
            return value

        for opt in self.options[i]:
            if opt.value == value:
                return opt

        raise InvalidChoice(self, value)

    def _add_choice(self, choices, choice: Option):
        choices.append(choice.value)

    @staticmethod
    def _canonical_1d_form(choices: Union[MultiChoiceValue, EmptyValue]) -> \
            Union[List[ChoiceValue], EmptyValue]:
        if isinstance(choices, list) or choices is Value.EMPTY:
            return choices
        return [choices]

    @staticmethod
    def _is_choice_value(value):
        return isinstance(value, str) or isinstance(value, Option)


class SingleChoiceInput(ChoiceInput, ABC):
    def _validate(self):
        super()._validate()
        for i, choices in enumerate(self._values):
            if len(choices) > 1:
                raise MultipleValues(self, i)


class ChoiceInput1D(ChoiceInput, SingleInput, ABC):
    # checkboxes without "other"
    @property
    def options(self):
        return self._options[0]

    def _hints(self, indent=0):
        return [add_indent(f'- {opt.to_str()}', indent) for opt in self.options]


class OtherChoiceInput(ChoiceInput1D, ABC):
    """ChoiceInput which supports "Other" option"""
    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        options = []
        other_option = None
        for opt in res['options'][0]:
            if opt.other:
                other_option = opt
            else:
                options.append(opt)
        res.update({
            'options': [options],
            'other_option': other_option,
        })
        return res

    def __init__(self, *, other_option, **kwargs):
        super().__init__(**kwargs)
        self.other_option = other_option
        self._other_value: Union[str, None] = None

    def payload(self):
        if self._other_value is None:
            return super().payload()

        payload = super().payload()
        main_key = self._submit_id(self._entry_id)
        other_key = main_key + '.other_option_response'
        payload[main_key].append('__other_option__')
        payload[other_key] = [self._other_value]
        return payload

    def _set_choices(self, choices: List[Union[List[ChoiceValue], EmptyValue]]):
        self._other_value = None
        super()._set_choices(choices)

    def _find_option(self, value: ChoiceValue, i):  # i == 0
        if self.other_option is None:
            return super()._find_option(value, i)

        if isinstance(value, Option):
            if value.other and self._other_value is not None:
                raise DuplicateOther(self, self._other_value, value.value)
            return value

        for opt in self.options:
            if opt.value == value:
                return opt

        if self._other_value is not None:
            raise DuplicateOther(self, self._other_value, value)
        return self.other_option

    def _add_choice(self, choices, choice: Option):
        if choice.other:
            self._other_value = choice.value
        else:
            super()._add_choice(choices, choice)

    def _validate(self):
        if self.required and self._value is None:
            if self._other_value is None:
                raise RequiredElement(self)
            if not self._other_value:
                raise EmptyOther(self)

    def _hints(self, indent=0):
        hints = super()._hints()
        if self.other_option is not None:
            hints.append(add_indent(f'- {self.other_option.to_str()}', indent))
        return hints

    def _entry_answer(self, i) -> str:  # i == 0
        if self._other_value is None:
            return super()._entry_answer(i)
        val = f'"{self._other_value}"'
        if self._value:
            val = '{super()._entry_answer(i)}, {val}'
        return val


class Grid(ChoiceInput, ABC):
    class Index(InputElement.Index):
        ROW_NAME = 3
        MULTICHOICE = 11

    @staticmethod
    def parse_multichoice(elem):
        return bool(Grid._get_entries(elem)[0][Grid.Index.MULTICHOICE][0])

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        res.update({
            'rows': [entry[cls.Index.ROW_NAME][0] for entry in cls._get_entries(elem)]
        })
        return res

    def __init__(self, *, rows, **kwargs):
        super().__init__(**kwargs)
        self.rows = rows
        self.cols = self.options  # alias

    @property
    def options(self):
        return self._options[0]

    def _hints(self, indent=0):
        return [add_indent('  ' + ' | '.join([str(opt) for opt in self.options]), indent)] + \
               [add_indent(f'- {row}', indent) for row in self.rows]

    def _set_grid_values(self, values: Union[GridValue, EmptyValue]):
        # TODO check length and types
        if values is Value.EMPTY:
            return self._set_choices([Value.EMPTY] * len(self.rows))
        self._set_choices([self._canonical_1d_form(entry_value) for entry_value in values])


class TimeElement(SingleInput, ABC):
    class Index(SingleInput.Index):
        FLAGS = 6
        DURATION = 0

    @staticmethod
    def parse_duration_flag(elem):
        flags = TimeElement._get_value(elem)[TimeElement.Index.FLAGS]
        return bool(flags[TimeElement.Index.DURATION])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._hour = None
        self._minute = None
        self._second = None

    def payload(self):
        payload = {}
        if self._hour is not None:
            payload[self._part_id('hour')] = self._hour
        if self._minute is not None:
            payload[self._part_id('minute')] = self._minute
        if self._second is not None:
            payload[self._part_id('second')] = self._second
        return payload

    def _set_time(self, hour, minute, second):
        self._hour = hour
        self._minute = minute
        self._second = second
        self._validate()

    def _validate(self):
        if self.required and self._is_empty():
            raise RequiredElement(self)

    def _is_empty(self):
        return all(val is None for val in [self._hour, self._minute, self._second])


class DateElement(SingleInput, ABC):
    class Index(SingleInput.Index):
        FLAGS = 7
        TIME = 0
        YEAR = 1

    @staticmethod
    def parse_time_flag(elem):
        flags = DateElement._get_value(elem)[DateElement.Index.FLAGS]
        return bool(flags[DateElement.Index.TIME])

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        flags = cls._get_value(elem)[cls.Index.FLAGS]
        res.update({
            'has_year': bool(flags[cls.Index.YEAR])
        })
        return res

    def __init__(self, *, has_year, **kwargs):
        super().__init__(**kwargs)
        self.has_year = has_year
        self._date = None

    def payload(self):
        if self._date is None:
            return {}
        payload = {
            self._part_id('month'): self._date.month,
            self._part_id('day'): self._date.day,
        }
        if self.has_year:
            payload[self._part_id("year")] = self._date.year
        return payload

    def _set_date(self, value: Union[date, None]):
        self._date = value
        self._validate()

    def _validate(self):
        if self.required and self._date is None:
            raise RequiredElement(self)

    def _answer(self) -> List[str]:
        if self._date is None:
            return ['EMPTY']
        fmt = '%m/%d'
        if self.has_year:
            fmt = '%Y/' + fmt
        return [f'"{self._date.strftime(fmt)}"']


class MediaElement(Element):
    pass


class TextInput(SingleInput):
    def set_value(self, value: Union[TextValue, EmptyValue]):
        if value is Value.EMPTY:
            return self._set_value(value)
        if isinstance(value, str):
            return self._set_value([value])
        raise invalid_type(value)


class ActionChoiceInput(ChoiceInput1D, SingleChoiceInput):
    """ChoiceInput with optional actions based on choice"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.next_page = None

    def set_value(self, value: Union[ChoiceValue, EmptyValue]):
        if self._is_choice_value(value) or value is Value.EMPTY:
            return self._set_choices([self._canonical_1d_form(value)])
        raise invalid_type(value)

    def _set_choices(self, choices: List[Union[List[ChoiceValue], EmptyValue]]):
        self.next_page = None
        super()._set_choices(choices)

    def _add_choice(self, choices, choice: Option):
        super()._add_choice(choices, choice)
        if isinstance(choice, ActionOption):
            self.next_page = choice.next_page

    def _answer(self) -> List[str]:
        from .elements import Page
        answer = super()._answer()
        if self.next_page is not None:
            if self.next_page is Page.SUBMIT:
                answer.append('Go to SUBMIT')
            else:
                answer.append(f'Go to page {self.next_page.index + 1}')
        return answer

    def resolve_actions(self, next_page, mapping):
        for option in self.options:
            if isinstance(option, ActionOption):
                option.resolve_action(next_page, mapping)
