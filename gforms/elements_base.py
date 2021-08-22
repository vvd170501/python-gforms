from __future__ import annotations

from abc import ABC, abstractmethod

from enum import Enum, auto
from typing import Dict, List, Literal, Union, cast, Any, Optional, Tuple, TYPE_CHECKING

from .util import DefaultEnum, list_get
from .validators import Validator, GridValidator, TextValidator, GridTypes, NumberTypes
from .errors import DuplicateOther, EmptyOther, InvalidChoice, \
    ElementTypeError, ElementValueError, RequiredElement, RequiredRow, RowTypeError, \
    InvalidRowChoice, MisconfiguredElement
from .options import ActionOption, Option, parse as parse_option

if TYPE_CHECKING:
    from .form import Form


class Value(Enum):
    """A value which can be returned by a callback in Form.fill

    DEFAULT: Use the value returned by the default callback.
    EMPTY: Leave the element empty.
    UNCHANGED: Leave the element value unchanged.
    """

    DEFAULT = auto()
    EMPTY = auto()
    UNCHANGED = auto()


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


class _Action:
    FIRST = -1
    NEXT = -2
    SUBMIT = -3


class Element:
    """An element of a form.

    Attributes:
        id: The element ID.
        name: The element name (may be None)
        description: The element description (may be None).
        type: The element type.
    """

    class Type(DefaultEnum):
        UNKNOWN = -1
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
        FILE_UPLOAD = 13

    class _Index:
        ID = 0
        NAME = 1
        DESCRIPTION = 2
        TYPE = 3

    @classmethod
    def parse(cls, elem):
        """Creates an Element from its JSON representation.

        This method should not be called directly,
        use gforms.elements.parse instead.
        """
        return cls(**cls._parse(elem))

    @classmethod
    def _parse(cls, elem):
        return {
            'id_': elem[cls._Index.ID],
            'name': elem[cls._Index.NAME],
            'description': elem[cls._Index.DESCRIPTION],  # may be None
            'type_': Element.Type(elem[cls._Index.TYPE]),
        }

    def __init__(self, *, id_, name, description, type_):
        self.id = id_
        self.name = name
        self.description = description
        self.type = type_
        self._form: Optional['Form'] = None

    def bind(self, form):
        self._form = form

    def to_str(self, indent=0, **kwargs):
        """Returns a text representation of the element.

        For args description, see Form.to_str.
        """
        s = f'{self._type_str()}'
        if self.name:
            s = f'{s}: {self.name}'
        if self.description:
            s = f'{s}\n{self.description}'
        return s

    def _type_str(self):
        return type(self).__name__


class InputElement(Element, ABC):
    """An element which can be filled.

    Attributes:
        required: Self-explanatory.
    """

    class _Index(Element._Index):
        ENTRIES = 4
        ENTRY_ID = 0
        REQUIRED = 2

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        entries = cls._get_entries(elem)
        res.update({
            'entry_ids': [e[cls._Index.ENTRY_ID] for e in entries],
            'required': bool(entries[0][cls._Index.REQUIRED]),  # same for all entries
        })
        return res

    def __init__(self, *, entry_ids, required, **kwargs):
        super().__init__(**kwargs)
        self._entry_ids = entry_ids
        self.required = required
        self._values: List[List[str]] = [[] for _ in self._entry_ids]

    @abstractmethod
    def set_value(self, value):
        """Sets the value for this element.

        All elements accept Value.EMPTY as an input.
        For other accepted types and values, see subclasses.

        Args:
            value: The value for this element.

        Raises:
            gforms.errors.ElementTypeError:
                The argument's type is not accepted by this element.
        """
        raise NotImplementedError()

    def validate(self):
        """Checks if the element has a valid value.

        Raises a ValidationError if the value is invalid.

        Raises:
            gforms.errors.RequiredElement:
                This element is required, but the value is empty.
            gforms.errors.InvalidValue:
                The value has a correct type,
                but is not valid for this element.
        """
        self._validate()
        if self._form is not None:
            self._form._unvalidated_elements.discard(self)

    def to_str(self, indent=0, include_answer=False):
        """See base class."""
        parts = self._header()
        hints = self._hints(indent, include_answer)
        if hints:
            parts.append('\n')
            parts.append('\n'.join(hints))
        if include_answer:
            answer = self._answer()
            if answer:
                parts.append('\n')
                parts.append('\n'.join(answer))
        return ''.join(parts)

    def payload(self) -> Dict[str, List[str]]:
        """Returns a payload which can be used in Form.submit

        The payload contains the element's value(s)
        and can be used as a (part of) POST request body.
        """
        payload = {}
        for entry_id, value in zip(self._entry_ids, self._values):
            if value:
                payload[self._submit_id(entry_id)] = value[:]
        return payload

    def draft(self) -> List[Tuple]:
        """Returns a (part of) emulated draftResponse for Form.submit."""
        result = []
        for entry_id, value in zip(self._entry_ids, self._values):
            if value:
                result.append((
                    None,  # ???
                    entry_id,
                    value[:],
                    0  # Last choice is "Other" (for "Individual responses" tab)
                ))
        return result

    def prefill(self, prefilled_data: Dict[str, List[str]]):
        """Fills the element with values from the prefilled link."""
        values = [prefilled_data.get(entry_id, []) for entry_id in self._entry_ids]
        # FIXME prefilled element on an skipped page doesn't need to be validated
        # prefilled data still needs to be validated
        # (e.g. a modified url was used or elements were updated)
        if any(values):  # Don't invalidate an element if it's not prefilled. Find a better solution?
            self._set_values(values)

    @staticmethod
    def _submit_id(entry_id):
        return f'entry.{entry_id}'

    @staticmethod
    def _get_entries(elem):
        return elem[InputElement._Index.ENTRIES]

    def _is_empty(self):
        return not any(self._values)

    def _set_values(self, values: List[Union[List[str], EmptyValue]]):
        values = values[:]
        for i, entry_values in enumerate(values):
            if entry_values is Value.EMPTY:
                values[i] = []

        self._values = values  # type: ignore
        if self._form is not None:
            self._form._unvalidated_elements.add(self)

    def _header(self) -> List[str]:
        parts = [self._type_str()]
        if self.required:
            parts.append('*')
        if self.name:
            parts.append(f': {self.name}')
        if self.description:
            parts.append(f'\n{self.description}')
        return parts

    def _hints(self, indent=0, modify=False):
        """Returns input hints (options / values).

        Returned strings should be already indented.
        """
        return []

    def _answer(self) -> List[str]:
        return [f'> {self._entry_answer(i)}' for i in range(len(self._entry_ids))]

    def _entry_answer(self, i) -> str:
        entry_val = self._values[i]
        if not entry_val:
            return 'EMPTY'
        return ', '.join(f'"{value}"' for value in entry_val)

    def _validate(self):
        for i in range(len(self._values)):
            self._validate_entry(i)

    def _validate_entry(self, index):
        if self.required and not self._values[index]:
            raise RequiredElement(self, index=index)


class SingleInput(InputElement):
    """An InputElement with a single entry."""

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
    def _get_entry(elem):
        return InputElement._get_entries(elem)[0]


class ChoiceInput(InputElement, ABC):
    """An input element which has a predefined set of options.

    Attributes:
        options: A list of allowed choices for this element.
    """

    class _Index(InputElement._Index):
        OPTIONS = 1

    # This class is basically the same as CheckboxGrid
    _has_multichoice = False

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        options = [
            [
                parse_option(opt) for opt in entry[cls._Index.OPTIONS]
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

    def _hints(self, indent=0, modify=False):
        return []

    def _find_option(self, value: ChoiceValue, i):
        if isinstance(value, Option):
            # assuming value was chosen from self.options
            return value

        for opt in self._options[i]:
            if opt.value == value:
                return opt

        raise InvalidChoice(self, value, index=i)

    def _add_choice(self, choices, choice: Option):
        choices.append(choice.value)

    def _to_choice_list(self, choices: Union[MultiChoiceValue, EmptyValue, Any])\
            -> Union[List[ChoiceValue], EmptyValue]:
        if choices is Value.EMPTY:
            return choices
        elif isinstance(choices, list):
            if not self._has_multichoice:
                raise ElementTypeError(self, choices)
            for choice in choices:
                if not ChoiceInput._is_choice_value(choice):
                    raise ElementTypeError(self, choices)
            return choices
        elif ChoiceInput._is_choice_value(choices):
            return [choices]
        raise ElementTypeError(self, choices)

    @staticmethod
    def _is_choice_value(value):
        return isinstance(value, str) or isinstance(value, Option)


class MultiChoiceInput(ChoiceInput):
    """A ChoiceInput which can accept multiple values."""

    _has_multichoice = True


class ChoiceInput1D(ChoiceInput, SingleInput):
    """A ChoiceInput with a single entry.

    Attributes:
        shuffle_options: Self-explanatory..
    """

    # ChoiceInput1D == Checkboxes without "other"
    _choice_symbols = ('·', '>')

    class _Index(ChoiceInput._Index):
        SHUFFLE_OPTIONS = 8  # Does not affect Scale

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        res.update({
            'shuffle_options': bool(list_get(cls._get_entry(elem), cls._Index.SHUFFLE_OPTIONS, False)),
        })
        return res

    def __init__(self, *, shuffle_options, **kwargs):
        super().__init__(**kwargs)
        self.shuffle_options = shuffle_options


    @property
    def options(self):
        return self._options[0]

    def _hints(self, indent=0, modify=False):
        if modify:
            return [
                f'{self._choice_symbols[opt.value in self._value]} {opt.to_str()}'
                for opt in self.options
            ]
        else:
            return [f'{self._choice_symbols[0]} {opt.to_str()}' for opt in self.options]

    def _answer(self):
        return []


class OtherChoiceInput(ChoiceInput1D):
    """A ChoiceInput1D which may have an "Other" option.

    Attributes:
        other_option: The "Other" option, if it exists.
    """

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

    def payload(self) -> Dict[str, List[str]]:
        """See base class."""
        payload = super().payload()
        # '' is not converted to None (see _validate_entry), so "... not None" isn't applicable
        if not self._other_value:
            return payload

        main_key = self._submit_id(self._entry_id)
        other_key = main_key + '.other_option_response'
        payload.setdefault(main_key, []).append('__other_option__')
        payload[other_key] = [self._other_value]
        return payload

    def draft(self) -> List[Tuple]:
        """See base class."""
        result = super().draft()
        if not self._other_value:
            return result

        if not result:
            result.append((None, self._entry_id, [self._other_value], 1))
            return result
        *data, answers, _ = result[0]
        answers.append(self._other_value)
        result[0] = (*data, answers, 1)
        return result

    def _is_empty(self):
        return super()._is_empty() and self._other_value is None

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
        self.other_option.value = value
        return self.other_option

    def _add_choice(self, choices, choice: Option):
        if choice.other:
            self._other_value = choice.value
        else:
            super()._add_choice(choices, choice)

    def _validate_entry(self, index):
        if self.required and not self._value:
            if self._other_value is None:
                raise RequiredElement(self)
            if not self._other_value:
                raise EmptyOther(self)

    def _hints(self, indent=0, modify=False):
        hints = super()._hints(indent, modify)
        if self.other_option is not None:
            if modify and self._other_value is not None:
                hints.append(
                    f'{self._choice_symbols[1]}'
                    f' {self.other_option.to_str(with_value=self._other_value)}'
                )
            else:
                hints.append(f'{self._choice_symbols[0]} {self.other_option.to_str()}')
        return hints


class ValidatedInput(InputElement, ABC):
    """An input element which may have a validator.

    Attributes:
        validator: The validator, if it exists.
    """

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        res.update({
            'validator': cls._parse_validator(elem)
        })
        return res

    def __init__(self, *, validator, **kwargs):
        super().__init__(**kwargs)
        self.validator: Optional[Validator] = validator

    def is_misconfigured(self):
        """Checks if the element cannot be filled with a valid value."""
        if self.validator is None:
            return False
        if self.validator.has_unknown_type() or self.validator.bad_args:
            return False
        if not self.required:  # always can set empty value
            return False
        return self._is_misconfigured()

    def _validate(self):
        """See base validate method.

        If this element is required and MisconfiguredElement is raised,
        you should skip the page with this element, if possible.
        Otherwise, the form is not submittable.

        Raises:
            gforms.errors.MisconfiguredElement:
                This element will not accept any non-empty value.
        """
        if self.is_misconfigured():
            raise MisconfiguredElement(self)
        super()._validate()
        if self.validator is not None and not self._is_empty():  # Non-empty value
            self.validator.validate(self)

    def _hints(self, indent=0, modify=False):
        res = []
        if self.validator is not None:
            res.append(f'! {self.validator.to_str()} !')
        return res + super()._hints(indent, modify)

    @classmethod
    @abstractmethod
    def _parse_validator(cls, elem) -> Optional[Validator]:
        raise NotImplementedError()

    @abstractmethod
    def _is_misconfigured(self):
        # NOTE method is called only when self.validator is not None and self.required is True
        raise NotImplementedError()


class Grid(ValidatedInput, ChoiceInput):
    """A Grid input element.

    Attributes:
        rows: The grid row names.
        cols: The grid columns (an alias for options).
        shuffle_rows: Shuffle this grid's rows.
    """

    _cell_symbols = ('?', '+')

    class _Index(ChoiceInput._Index):
        SHUFFLE_ROWS = 7
        VALIDATOR = 8
        ROW_NAME = 3
        MULTICHOICE = 11

    @staticmethod
    def parse_multichoice(elem):
        return bool(Grid._get_entries(elem)[0][Grid._Index.MULTICHOICE][0])

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        res.update({
            'rows': [entry[cls._Index.ROW_NAME][0] for entry in cls._get_entries(elem)],
            'shuffle_rows': bool(list_get(elem, cls._Index.SHUFFLE_ROWS, False)),
        })
        return res

    @classmethod
    def _parse_validator(cls, elem) -> Optional[GridValidator]:
        if len(elem) > cls._Index.VALIDATOR and elem[cls._Index.VALIDATOR]:
            return GridValidator.parse(elem[cls._Index.VALIDATOR][0])
        return None

    def __init__(self, *, rows, shuffle_rows, **kwargs):
        super().__init__(**kwargs)
        self.rows = rows
        self.cols = self.options  # alias
        self.shuffle_rows = shuffle_rows

    @property
    def options(self):
        return self._options[0]

    def _is_misconfigured(self):
        return self.validator.subtype is GridTypes.EXCLUSIVE_COLUMNS \
            and len(self.cols) < len(self.rows)

    def _hints(self, indent=0, modify=False):
        # NOTE row/column names may need wrapping
        res = super()._hints(indent, modify)
        max_length = max(len(row) for row in self.rows)
        header = ' ' * (max_length + 1) + '|'.join([opt.value for opt in self.options])
        row_fmt = f'{{:>{max_length}}} ' + \
                  ' '.join(f'{{:^{len(col.value)}}}' for col in self.cols)

        if not modify:
            cells = [[self._cell_symbols[0]] * len(self.options)] * len(self.rows)
        else:
            cells = [None] * len(self.rows)
            for i, row_choices in enumerate(self._values):
                cells[i] = [
                    self._cell_symbols[opt.value in row_choices]
                    for opt in self.options
                ]

        res.append(header)
        res += [row_fmt.format(row, *row_cells) for row, row_cells in zip(self.rows, cells)]
        return res

    def _answer(self):
        return []

    def _set_grid_values(self, values: Union[GridValue, EmptyValue]):
        if values is Value.EMPTY:
            return self._set_choices([Value.EMPTY] * len(self.rows))
        if not isinstance(values, list):
            raise ElementTypeError(self, values)
        if len(values) != len(self.rows):
            raise ElementValueError(self, values,
                                    details='Length of choices does not match the number of rows')
        choices = []
        for i, entry_value in enumerate(values):
            try:
                choices.append(self._to_choice_list(entry_value))
            except ElementTypeError as e:
                raise RowTypeError(self, e.value, index=i) from e
        try:
            self._set_choices(choices)
        except InvalidChoice as e:
            raise InvalidRowChoice(self, e.value, index=e.index) from e

    def _validate_entry(self, index):
        try:
            super()._validate_entry(index)
        except RequiredElement as e:
            raise RequiredRow(self, index=e.index)


class TimeInput(SingleInput):
    """An element which represents a time or a duration."""

    class _Index(SingleInput._Index):
        FLAGS = 6
        DURATION = 0

    @staticmethod
    def parse_duration_flag(elem):
        flags = TimeInput._get_entry(elem)[TimeInput._Index.FLAGS]
        return bool(flags[TimeInput._Index.DURATION])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._hour = None
        self._minute = None
        self._second = None

    def payload(self) -> Dict[str, List[str]]:
        """See base class."""
        payload = {}
        if self._hour is not None:
            payload[self._part_id('hour')] = self._hour
        if self._minute is not None:
            payload[self._part_id('minute')] = self._minute
        if self._second is not None:
            payload[self._part_id('second')] = self._second
        return payload

    def draft(self) -> List[Tuple]:
        """See base class."""
        hms = []
        for val in [self._hour, self._minute, self._second]:
            if val is not None:
                hms.append(f'{val:02}')
        # will return an empty string for an empty element.
        # The server sets the same draft value, so it's ok
        return [(None, self._entry_id, [':'.join(hms)], 0)]

    def _validate(self):
        if self.required and self._is_empty():
            raise RequiredElement(self)

    def _set_time(self, hour, minute, second):
        self._hour = hour
        self._minute = minute
        self._second = second

    def _is_empty(self):
        return all(val is None for val in [self._hour, self._minute, self._second])


class DateInput(SingleInput):
    """An element which represents a date.

    Attributes:
        has_year: Whether or not this element has a year field.
    """

    class _Index(SingleInput._Index):
        FLAGS = 7
        TIME = 0
        YEAR = 1

    @staticmethod
    def parse_time_flag(elem):
        flags = DateInput._get_entry(elem)[DateInput._Index.FLAGS]
        return bool(flags[DateInput._Index.TIME])

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        flags = cls._get_entry(elem)[cls._Index.FLAGS]
        res.update({
            'has_year': bool(flags[cls._Index.YEAR])
        })
        return res

    def __init__(self, *, has_year, **kwargs):
        super().__init__(**kwargs)
        self.has_year = has_year
        self._date = None

    def payload(self) -> Dict[str, List[str]]:
        """See base class."""
        if self._date is None:
            return {}
        payload = {
            self._part_id('month'): self._date.month,
            self._part_id('day'): self._date.day,
        }
        if self.has_year:
            payload[self._part_id("year")] = self._date.year
        return payload

    def draft(self) -> List[Tuple]:
        """See base class."""
        if self._date is None:
            return []
        fmt = '%Y-%m-%d' if self.has_year else '%m-%d'
        return [(None, self._entry_id, [self._date.strftime(fmt)], 0)]

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

    def _is_empty(self):
        return self._date is None


class MediaElement(Element):
    """A base class for media elements."""

    pass


class TextInput(ValidatedInput, SingleInput):
    """An element which accepts text input."""

    class _Index(SingleInput._Index):
        VALIDATOR = 4

    @classmethod
    def _parse_validator(cls, elem) -> Optional[TextValidator]:
        value = cls._get_entry(elem)
        if len(value) > cls._Index.VALIDATOR and value[cls._Index.VALIDATOR]:
            return TextValidator.parse(value[cls._Index.VALIDATOR][0])
        return None

    def set_value(self, value: Union[TextValue, EmptyValue]):
        """Sets the value for this element.

        Accepts a string or an empty value.

        Args:
            value: The value for this element.

        Raises:
            gforms.errors.ElementTypeError:
                The argument's type is not accepted by this element.
        """
        if isinstance(value, str):
            if not value:
                value = Value.EMPTY
            else:
                return self._set_value([value])
        if value is Value.EMPTY:
            return self._set_value(value)
        raise ElementTypeError(self, value)

    def _is_misconfigured(self):
        return self.validator.subtype is NumberTypes.RANGE \
            and self.validator.args[0] > self.validator.args[1]


class ActionChoiceInput(ChoiceInput1D):
    """A ChoiceInput1D with optional actions based on choice.

    Attributes:
        next_page: The next page, based on user's choice.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.next_page = None

    def set_value(self, value: Union[ChoiceValue, EmptyValue]):
        """Sets the value for this element.

        Accepts an Option, a string or an empty value.

        Args:
            value: The value for this element.

        Raises:
            gforms.errors.ElementTypeError:
                The argument's type is not accepted by this element.
        """
        return self._set_choices([self._to_choice_list(value)])

    def _set_choices(self, choices: List[Union[List[ChoiceValue], EmptyValue]]):
        self.next_page = None
        super()._set_choices(choices)
        # Don't reset no_loops if the element's options have no actions or the actions are ignored
        if (self._form is not None and
                isinstance(self.options[0], ActionOption) and
                cast(ActionOption, self.options[0]).next_page is not None):
            self._form._no_loops = False

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

    def _resolve_actions(self, next_page, mapping):
        for option in self.options:
            if isinstance(option, ActionOption):
                option._resolve_action(next_page, mapping)
