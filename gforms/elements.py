from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from typing import List, Union, Optional, Dict, Tuple

from .elements_base import _Action, Value, MultiChoiceInput
from .elements_base import Element, MediaElement, InputElement, \
                           ActionChoiceInput, ChoiceInput, ChoiceInput1D, \
                           OtherChoiceInput, ValidatedInput, TextInput, \
                           DateElement, Grid, TimeElement
from .elements_base import ChoiceValue, EmptyValue, MultiChoiceValue, TextValue, \
                           GridChoiceValue, GridMultiChoiceValue

from .errors import ElementTypeError, InvalidDuration, \
    RequiredElement, InvalidText, MisconfiguredElement, UnknownValidator, InvalidArguments
from .options import ActionOption
from .util import RADIO_SYMBOLS, CHECKBOX_SYMBOLS, add_indent, elem_separator, random_subset
from .validators import CheckboxValidator, CheckboxTypes


__all__ = ['Element', '_Action', 'CallbackRetVal', 'Value',
           'Page', 'Comment', 'Image', 'Video',
           'Short', 'Paragraph', 'Radio', 'Dropdown', 'Checkboxes', 'Scale',
           'RadioGrid', 'CheckboxGrid',
           'Time', 'Duration', 'Date', 'DateTime',
           'default_callback', 'parse']


CheckboxesValue = MultiChoiceValue
ScaleValue = Union[ChoiceValue, int]
RadioGridValue = GridChoiceValue
CheckboxGridValue = GridMultiChoiceValue
DateValue = date
DateTimeValue = datetime
TimeValue = time
DurationValue = timedelta

ElemValue = Union[
    TextValue,  # Short, Paragraph
    ChoiceValue,  # Radio, Dropdown
    CheckboxesValue,
    ScaleValue,
    RadioGridValue,
    CheckboxGridValue,
    DateValue,
    DateTimeValue,
    TimeValue,
    DurationValue,
]

CallbackRetVal = Union[ElemValue, Value]


class Page(Element):
    """A Page element.

    Attributes:
        index: Index of the page.
        elements: A list of elements contained within the page.
    """

    class _Index(Element._Index):
        ACTION = 5

    SUBMIT: Optional[Page] = None

    @classmethod
    def first(cls):
        return cls(
            id_=_Action.FIRST,
            name=None,
            description=None,
            type_=Element.Type.PAGE,
            prev_action=_Action.NEXT,  # ignored
        ).with_index(0)

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        res['prev_action'] = _Action.NEXT
        if len(elem) > cls._Index.ACTION:
            # FIRST / NEXT / SUBMIT / page id
            res['prev_action'] = elem[cls._Index.ACTION]
        return res

    def __init__(self, *, prev_action, **kwargs):
        super().__init__(**kwargs)
        self._prev_action = prev_action
        self._next_page = None
        self._has_default_next_page = True
        self.index = None
        self.elements = []

    def with_index(self, index):
        self.index = index
        return self

    def append(self, elem):
        self.elements.append(elem)

    def next_page(self):
        """The next pge, based on user's choices."""
        if self._next_page is None:
            return None

        next_page = self._next_page
        for elem in self.elements:
            if isinstance(elem, ActionChoiceInput) and elem.next_page is not None:
                next_page = elem.next_page
        return next_page

    def to_str(self, indent=0, include_answer=False):
        """See base class."""
        title = f'Page {self.index + 1}:'
        if self.name:
            title = f'{title} {self.name}'
        if self.description:
            title = f'{title}\n{self.description}'
        if not self._has_default_next_page:
            if self._next_page is None:
                title = f'{title} -> Submit'
            else:
                title = f'{title} -> Page {self._next_page.index + 1}'
        if not self.elements:
            return title
        separator = elem_separator(indent)
        return '\n'.join(
            [title] +
            [
                separator + '\n' +
                add_indent(elem.to_str(indent=indent, include_answer=include_answer), indent)
                for elem in self.elements
            ]
        )

    def payload(self) -> Dict[str, List[str]]:
        """Returns a combined payload of all elements from this page."""
        payload = {}
        for elem in self.elements:
            if isinstance(elem, InputElement):
                payload.update(elem.payload())
        return payload

    def draft(self) -> List[Tuple]:
        """Returns a combined draftResponse."""
        result = []
        for elem in self.elements:
            if isinstance(elem, InputElement):
                result += elem.draft()
        return result

    def _resolve_actions(self, next_page: Page, mapping):
        for elem in self.elements:
            if isinstance(elem, ActionChoiceInput):
                elem._resolve_actions(next_page, mapping)

        if next_page is None:
            return
        if next_page._prev_action == _Action.SUBMIT:
            self._has_default_next_page = False
            return

        if next_page._prev_action == _Action.NEXT:
            self._next_page = next_page
        else:
            self._next_page = mapping[next_page._prev_action]
            self._has_default_next_page = False


Page.SUBMIT = Page(id_=_Action.SUBMIT, name=None, description=None,
                   type_=Element.Type.PAGE, prev_action=None).with_index(_Action.SUBMIT)


class Comment(Element):
    pass


class Image(MediaElement):
    # elem[6][0] - cosmoId (no direct link?)
    # search "google docs cosmoid" for more details
    # NOTE some input elements or options may contain attached images (parsing is not implemented)
    pass


class Video(MediaElement):
    class _Index(MediaElement._Index):
        VIDEO = 6
        LINK = 3

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        res.update({
            'link': elem[cls._Index.VIDEO][cls._Index.LINK]
        })
        return res

    def __init__(self, *, link, **kwargs):
        super().__init__(**kwargs)
        self._link = link

    def url(self):
        return f'https://youtu.be/{self._link}'

    def to_str(self, indent=0, **kwargs):
        s = super().to_str(indent, **kwargs)
        return f'{s}\n{self.url()}'


class Short(TextInput):
    """A single-line text input."""

    def _validate_entry(self, index):
        super()._validate_entry(index)
        if not self._value:
            return
        value = self._value[0]
        if '\n' in value:
            raise InvalidText(self, value.replace('\n', r'\n'), 'Input contains newlines')


class Paragraph(TextInput):
    """A multi-line text input."""

    pass


class Radio(ActionChoiceInput, OtherChoiceInput):
    _choice_symbols = RADIO_SYMBOLS

    def _resolve_actions(self, next_page, mapping):
        if isinstance(self.other_option, ActionOption):
            self.other_option._resolve_action(next_page, mapping)
        super()._resolve_actions(next_page, mapping)


class Dropdown(ActionChoiceInput):
    pass


class Checkboxes(ValidatedInput, OtherChoiceInput, MultiChoiceInput):
    _choice_symbols = CHECKBOX_SYMBOLS

    class _Index(ChoiceInput._Index):
        VALIDATOR = 4

    @classmethod
    def _parse_validator(cls, elem) -> Optional[CheckboxValidator]:
        value = cls._get_entry(elem)
        if len(value) > cls._Index.VALIDATOR and value[cls._Index.VALIDATOR]:
            return CheckboxValidator.parse(value[cls._Index.VALIDATOR][0])
        return None

    def set_value(self, value: Union[CheckboxesValue, EmptyValue]):
        """Sets the value for this element.

        Accepts a choice value (a string or an Option),
        a list of choice values or an empty value.

        Args:
            value: The value for this element.

        Raises:
            gforms.errors.ElementTypeError:
                The argument's type is not accepted by this element.
        """
        return self._set_choices([self._to_choice_list(value)])

    def _is_misconfigured(self):
        cnt = len(self.options)
        if self.other_option is not None:
            cnt += 1
        required = self.validator.args[0]  # always > 0
        if (self.validator.subtype is CheckboxTypes.AT_LEAST
                or self.validator.subtype is CheckboxTypes.EXACTLY) and cnt < required:
            return True
        return False


class Scale(ChoiceInput1D):
    """A liner scale.

    Attributes:
        low: The label for the lowest value (may be empty).
        high: The label for the highest value (may be empty).
    """

    class _Index(ChoiceInput._Index):
        LABELS = 3

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        low, high = cls._get_entry(elem)[cls._Index.LABELS]
        res.update({
            'low': low,
            'high': high,
        })
        return res

    def __init__(self, *, low, high, **kwargs):
        super().__init__(**kwargs)
        self.low = low
        self.high = high

    def set_value(self, value: Union[ScaleValue, EmptyValue]):
        """Sets the value for this element.

        Accepts a string, an Option, an int or an empty value.

        Args:
            value: The value for this element.

        Raises:
            gforms.errors.ElementTypeError:
                The argument's type is not accepted by this element.
        """
        if isinstance(value, int):
            value = str(value)
        return self._set_choices([self._to_choice_list(value)])

    def _hints(self, indent=0, modify=False):
        max_len = 1 if len(self.options) < 10 else 2
        tab = ' ' * (len(self.low) + 1) if self.low else ''
        header = tab + ' '.join([f'{opt.value:^{max_len}}' for opt in self.options])
        scale = [f'{RADIO_SYMBOLS[0]:^{max_len}}' for _ in self.options]
        if modify and self._value:
            scale[int(self._value[0]) - 1] = f'{RADIO_SYMBOLS[1]:^{max_len}}'
        scale = ' '.join(scale)
        if self.low:  # wrapping?
            scale = f'{self.low} {scale}'
        if self.high:
            scale = f'{scale} {self.high}'
        return [header, scale]

    def _answer(self):
        return []


class RadioGrid(Grid):
    _cell_symbols = RADIO_SYMBOLS

    def set_value(self, value: Union[RadioGridValue, EmptyValue]):
        """Sets the value for this element.

        Accepts an empty value or a list of choice values,
        each of which is a string, an Option or an empty value

        Args:
            value: The value for this element.

        Raises:
            gforms.errors.ElementTypeError:
                The argument's type is not accepted by this element.
            gforms.errors.ElementValueError:
                The argument is a list,
                but its length does not match the number of rows.
        """
        # REL_TODO Maybe it's better to allow list of lists with lengths <= 1
        #   e.g. grid.set_value([[val1], [], [val3], ...])
        #   instead of grid.set_value([val1, Value.EMPTY, val3, ...])
        self._set_grid_values(value)


class CheckboxGrid(Grid, MultiChoiceInput):
    _cell_symbols = CHECKBOX_SYMBOLS

    def set_value(self, value: Union[CheckboxGridValue, EmptyValue]):
        """Sets the value for this element.

        Accepts the same values as RadioGrid, but also
        allows each list element to be a list of strings or Option objects.

        Args:
            value: The value for this element.

        Raises:
            gforms.errors.ElementTypeError:
                The argument's type is not accepted by this element.
            gforms.errors.ElementValueError:
                The argument is a list,
                but its length does not match the number of rows.
        """
        self._set_grid_values(value)


class Time(TimeElement):
    def set_value(self, value: Union[TimeValue, EmptyValue]):
        """Sets the value for this element.

        Accepts a datetime.time or an empty value.

        Args:
            value: The value for this element.

        Raises:
            gforms.errors.ElementTypeError:
                The argument's type is not accepted by this element.
        """
        if value is Value.EMPTY:
            return self._set_time(None, None, None)
        if isinstance(value, time):
            return self._set_time(value.hour, value.minute, None)
        raise ElementTypeError(self, value)

    def _answer(self) -> List[str]:
        if self._is_empty():
            return ['EMPTY']
        return [f'{self._hour:02}:{self._minute:02}']


class Duration(TimeElement):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._timedelta = None

    def set_value(self, value: Union[DurationValue, EmptyValue]):
        """Sets the value for this element.

        Accepts a datetime.timedelta or an empty value.

        Args:
            value: The value for this element.

        Raises:
            gforms.errors.ElementTypeError:
                The argument's type is not accepted by this element.
        """
        if value is Value.EMPTY:
            self._set_time(None, None, None)
            self._timedelta = None
        elif isinstance(value, timedelta):
            seconds = int(value.total_seconds())
            h, m, s = seconds // 3600, seconds // 60 % 60, seconds % 60
            self._set_time(h, m, s)
            self._timedelta = value
        else:
            raise ElementTypeError(self, value)

    def validate(self):
        """See base class."""
        super().validate()
        if self._timedelta is None:
            return
        seconds = self._timedelta.total_seconds()
        if seconds >= 73 * 3600 or seconds < 0:
            raise InvalidDuration(self, self._timedelta)

    def _answer(self) -> List[str]:
        if self._is_empty():
            return ['EMPTY']
        h = self._hour or 0
        m = self._minute or 0
        s = self._second or 0
        return [f'{h:02}:{m:02}:{s:02}']


class Date(DateElement):
    def set_value(self, value: Union[DateValue, EmptyValue]):
        """Sets the value for this element.

        Accepts a datetime.date or an empty value.

        Args:
            value: The value for this element.

        Raises:
            gforms.errors.ElementTypeError:
                The argument's type is not accepted by this element.
        """
        if value is Value.EMPTY:
            self._date = None
        elif isinstance(value, date):
            self._date = value
        else:
            raise ElementTypeError(self, value)


class DateTime(DateElement):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._time = None

    def set_value(self, value: Union[DateTimeValue, EmptyValue]):
        """Sets the value for this element.

        Accepts a datetime.datetime or an empty value.

        Args:
            value: The value for this element.

        Raises:
            gforms.errors.ElementTypeError:
                The argument's type is not accepted by this element.
        """
        if value is Value.EMPTY:
            date_ = time_ = None
        elif isinstance(value, datetime):
            date_, time_ = value.date(), value.time()
        else:
            raise ElementTypeError(self, value)
        self._date = date_
        self._time = time_

    def payload(self) -> Dict[str, List[str]]:
        """See base class."""
        if self._date is None:
            return {}
        payload = super().payload()
        payload.update({
            self._part_id("hour"): self._time.hour,
            self._part_id("minute"): self._time.minute,
        })
        return payload

    def draft(self) -> List[Tuple]:
        """See base class."""
        if self._date is None:
            return []
        result = super().draft()
        date_str = result[0][2][0]  # add DraftIndex class?
        result[0][2][0] = date_str + f' {self._time.strftime("%H:%M")}'
        return result

    def validate(self):
        """See base class."""
        super().validate()
        if self.required and self._time is None:
            raise RequiredElement(self)

    def _answer(self) -> List[str]:
        if self._date is None:
            return ['EMPTY']
        answer = super()._answer()
        answer[0] += f' {self._time.strftime("%H:%M")}'
        return answer


def _grid_validated_choices(elem: Grid):
    # REL_TODO this function will choose maximal allowed number of columns,
    #   even if required is False (find a better solution or disable this feature entirely?)

    n = len(elem.rows)
    if isinstance(elem, RadioGrid):
        if len(elem.options) >= n:
            return random.sample(elem.options, k=n)
        # cols < rows
        # elem is not required (checked in default_callback by elem.is_misconfigured)
        row_indices = random.sample(range(n), k=len(elem.options))
        choices = [Value.EMPTY for _ in range(n)]
        for opt, idx in zip(elem.options, row_indices):
            choices[idx] = opt
        return choices

    # CheckboxGrid
    if not elem.required:
        # each column is chosen in a single (random) row
        row_indices = random.choices(range(n), k=len(elem.options))
        choices = [[] for _ in range(n)]
        for opt, idx in zip(elem.options, row_indices):
            choices[idx].append(opt)
        return choices

    # Required CheckboxGrid
    choices = random.sample(elem.options, k=n)
    res = [[choice] for choice in choices]  # choose at least one option in each row
    remaining = set(elem.options) - set(choices)
    if not remaining:
        return res
    # assign all remaining columns to random rows
    row_indices = random.choices(range(n), k=len(remaining))
    for opt, idx in zip(remaining, row_indices):
        res[idx].append(opt)
    return res


def _cb_validated_choices(elem: Checkboxes):
    required = elem.validator.args[0]
    if elem.validator.subtype is CheckboxTypes.AT_MOST:
        return random_subset(elem.options, max_size=required)
    if len(elem.options) < required:
        raise NotImplementedError('Need to choose "Other" value to meet validation requirements')
    if elem.validator.subtype is CheckboxTypes.AT_LEAST:
        return random_subset(elem.options, min_size=required)
    if elem.validator.subtype is CheckboxTypes.EXACTLY:
        return random.sample(elem.options, required)


def _validated_choices(elem):
    if isinstance(elem, Grid):
        return _grid_validated_choices(elem)
    if isinstance(elem, Checkboxes):
        return _cb_validated_choices(elem)
    raise NotImplementedError()


def default_callback(elem: InputElement, page_index, elem_index) -> Union[ElemValue, EmptyValue]:
    """The default callback implementation for Form.fill."""

    # Single choice inputs
    if isinstance(elem, Scale) or isinstance(elem, Dropdown) or isinstance(elem, Radio):
        opts = elem.options[:]
        if not elem.required:
            opts.append(Value.EMPTY)
        return random.choice(opts)

    # Example: allow "Other" in Radio
    #     if elem.other_option is not None:
    #         opt = random.choice(elem.options + [elem.other_option])
    #         if opt.other:
    #             # return 'Sample text'  # another alternative
    #             opt.value = 'Sample text'
    #         return opt

    # Check the validator; for TextInput raise NotImplementedError (later)
    if isinstance(elem, ValidatedInput) and not isinstance(elem, TextInput) \
            and elem.validator is not None:

        if elem.is_misconfigured():
            if elem.required:
                raise MisconfiguredElement(elem)
            return Value.EMPTY
        if elem.validator.has_unknown_type():
            # Raise, not warn. Otherwise, most probably, form submission will fail
            # If needed, custom callback should handle such cases
            raise UnknownValidator(
                type(elem.validator), [elem.validator.type, elem.validator.subtype]
            )
        if elem.validator.bad_args:
            raise InvalidArguments(
                type(elem.validator), elem.validator.type,
                elem.validator.subtype, elem.validator.args
            )
        return _validated_choices(elem)

    if isinstance(elem, Checkboxes):
        # Don't auto-choose "Other"
        return random_subset(elem.options, min_size=int(elem.required))

    if isinstance(elem, Grid):
        n = len(elem.rows)
        if isinstance(elem, CheckboxGrid):
            return [random_subset(elem.options, min_size=int(elem.required)) for _ in range(n)]
        opts = elem.options
        if not elem.required:
            opts = opts + [Value.EMPTY]
        return [random.choice(opts) for _ in range(n)]

    # text inputs / Date / DateTime / Time / Duration
    raise NotImplementedError(f'Cannot choose a random value for {elem._type_str()}')


_element_mapping = {getattr(Element.Type, el_type.__name__.upper()): el_type for el_type in [
    Short, Paragraph,
    Radio, Dropdown, Checkboxes, Scale,
    Comment, Page, Image, Video,
]}


def parse(elem):
    """Creates an Element of the right type from its JSON representation."""
    el_type = Element.Type(elem[Element._Index.TYPE])
    if el_type is Element.Type.GRID:
        cls = CheckboxGrid if Grid.parse_multichoice(elem) else RadioGrid
    elif el_type is Element.Type.DATE:
        cls = DateTime if DateElement.parse_time_flag(elem) else Date
    elif el_type is Element.Type.TIME:
        cls = Duration if TimeElement.parse_duration_flag(elem) else Time
    else:
        cls = _element_mapping[el_type]
    return cls.parse(elem)
