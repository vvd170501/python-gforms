from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from typing import List, Union, Optional

from .elements_base import Action, ElementType, Value
from .elements_base import Element, MediaElement, InputElement, \
                           ActionChoiceInput, ChoiceInput, ChoiceInput1D, \
                           OtherChoiceInput, SingleChoiceInput, TextInput, \
                           DateElement, Grid, TimeElement
from .elements_base import ChoiceValue, EmptyValue, MultiChoiceValue, TextValue, \
                           GridChoiceValue, GridMultiChoiceValue

from .errors import IncompatibleType, InvalidDuration, MultipleRowValues, MultipleValues, \
    RequiredElement, RequiredRow, InvalidText
from .options import ActionOption
from .util import add_indent, elem_separator, random_subset


__all__ = ['ElementType', 'Action', 'CallbackRetVal', 'Value',
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
    class Index(Element.Index):
        ACTION = 5

    SUBMIT: Optional[Page] = None

    @classmethod
    def first(cls):
        return cls(
            id_=Action.FIRST,
            name=None,
            description=None,
            type_=ElementType.PAGE,
            prev_action=Action.NEXT,  # ignored
        ).with_index(0)

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        res['prev_action'] = Action.NEXT
        if len(elem) > cls.Index.ACTION:
            res['prev_action'] = elem[cls.Index.ACTION]
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
        if self._next_page is None:
            return None

        next_page = self._next_page
        for elem in self.elements:
            if isinstance(elem, ActionChoiceInput) and elem.next_page is not None:
                next_page = elem.next_page
        return next_page

    def to_str(self, indent=0, include_answer=False):
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

    def resolve_actions(self, next_page: Page, mapping):
        for elem in self.elements:
            if isinstance(elem, ActionChoiceInput):
                elem.resolve_actions(next_page, mapping)

        if next_page is None:
            return
        if next_page._prev_action == Action.SUBMIT:
            self._has_default_next_page = False
            return

        if next_page._prev_action == Action.NEXT:
            self._next_page = next_page
        else:
            self._next_page = mapping[next_page._prev_action]
            self._has_default_next_page = False


Page.SUBMIT = Page(id_=Action.SUBMIT, name=None, description=None,
                   type_=ElementType.PAGE, prev_action=None).with_index(Action.SUBMIT)


class Comment(Element):
    pass


class Image(MediaElement):
    # elem[6][0] - cosmoId (no direct link?)
    # search "google docs cosmoid" for more details
    # NOTE some input elements or options may contain attached images (parsing is not implemented)
    pass


class Video(MediaElement):
    class Index(MediaElement.Index):
        VIDEO = 6
        LINK = 3

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        res.update({
            'link': elem[cls.Index.VIDEO][cls.Index.LINK]
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
    def _validate(self):
        super()._validate()
        if not self._value:
            return
        value = self._value[0]
        if '\n' in value:
            raise InvalidText(self, value.replace('\n', r'\n'), f'Input contains newlines')

    # For elements without additional validation, max value length is 32712 (tested on 15.05.21)
    # This limit may be dynamic


class Paragraph(TextInput):
    pass


class Radio(ActionChoiceInput, OtherChoiceInput):
    def resolve_actions(self, next_page, mapping):
        if isinstance(self.other_option, ActionOption):
            self.other_option.resolve_action(next_page, mapping)
        super().resolve_actions(next_page, mapping)


class Dropdown(ActionChoiceInput):
    pass


class Checkboxes(OtherChoiceInput):
    def set_value(self, value: Union[CheckboxesValue, EmptyValue]):
        return self._set_choices([self._valid_entry_choices(value)])


class Scale(ChoiceInput1D, SingleChoiceInput):
    class Index(ChoiceInput.Index):
        LABELS = 3

    @classmethod
    def _parse(cls, elem):
        res = super()._parse(elem)
        low, high = cls._get_value(elem)[cls.Index.LABELS]
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
        if isinstance(value, int):
            value = str(value)
        super().set_value(value)

    def _hints(self, indent=0):
        hint = f'{self.options[0]} - {self.options[-1]}'
        if self.low:
            hint = f'({self.low}) {hint}'
        if self.high:
            hint = f'{hint} ({self.high})'
        return [hint]


class RadioGrid(Grid, SingleChoiceInput):
    _cell_symbol = '◯'

    def set_value(self, value: Union[RadioGridValue, EmptyValue]):
        self._set_grid_values(value)

    def _validate(self):
        try:
            super()._validate()
        except MultipleValues as e:
            raise MultipleRowValues(self, index=e.index)
        except RequiredElement as e:
            raise RequiredRow(self, index=e.index)


class CheckboxGrid(Grid):
    _cell_symbol = '□'

    def set_value(self, value: Union[CheckboxGridValue, EmptyValue]):
        self._set_grid_values(value)


class Time(TimeElement):
    def set_value(self, value: Union[TimeValue, EmptyValue]):
        if value is Value.EMPTY:
            self._set_time(None, None, None)
        if isinstance(value, time):
            self._set_time(value.hour, value.minute, None)
        raise IncompatibleType(self, value)

    def _answer(self) -> List[str]:
        if self._is_empty():
            return ['EMPTY']
        return [f'{self._hour:02}:{self._minute:02}']


class Duration(TimeElement):
    def set_value(self, value: Union[DurationValue, EmptyValue]):
        if value is Value.EMPTY:
            self._set_time(None, None, None)
        if isinstance(value, timedelta):
            seconds = int(value.total_seconds())
            if seconds >= 73 * 3600 or seconds < 0:
                raise InvalidDuration(self, value)
            h, m, s = seconds // 3600, seconds // 60 % 60, seconds % 60
            self._set_time(h, m, s)
        raise IncompatibleType(self, value)

    def _answer(self) -> List[str]:
        if self._is_empty():
            return ['EMPTY']
        h = self._hour or 0
        m = self._minute or 0
        s = self._second or 0
        return [f'{h:02}:{m:02}:{s:02}']


class Date(DateElement):
    def set_value(self, value: Union[DateValue, EmptyValue]):
        if value is Value.EMPTY:
            return self._set_date(None)
        if isinstance(value, date):
            return self._set_date(value)
        raise IncompatibleType(self, value)


class DateTime(DateElement):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._time = None

    def set_value(self, value: Union[DateTimeValue, EmptyValue]):
        if value is Value.EMPTY:
            date_ = time_ = None
        elif isinstance(value, datetime):
            date_, time_ = value.date(), value.time()
        else:
            raise IncompatibleType(self, value)
        self._date = date_
        self._time = time_
        self._validate()

    def payload(self):
        if self._date is None:
            return {}
        payload = super().payload()
        payload.update({
            self._part_id("hour"): self._time.hour,
            self._part_id("minute"): self._time.minute,
        })
        return payload

    def _validate(self):
        if self.required and self._date is None or self._time is None:
            raise RequiredElement(self)

    def _answer(self) -> List[str]:
        if self._date is None:
            return ['EMPTY']
        answer = super()._answer()
        answer[0] += f' {self._time.strftime("%H:%M")}'
        return answer


def default_callback(elem: InputElement, page_index, elem_index) -> Union[ElemValue, EmptyValue]:
    if isinstance(elem, Scale) or isinstance(elem, Dropdown):
        return random.choice(elem.options)
    if isinstance(elem, Radio):
        # Don't auto-choose "Other"
        return random.choice(elem.options)

    # Example: allow "Other"
    #     if elem.other_option is not None:
    #         opt = random.choice(elem.options + [elem.other_option])
    #         if opt.other:
    #             # return 'Sample text'  # another alternative
    #             opt.value = 'Sample text'
    #         return opt

    if isinstance(elem, Checkboxes):
        # Don't auto-choose "Other"
        return random_subset(elem.options, nonempty=elem.required)

    if isinstance(elem, Grid):
        n = len(elem.rows)
        if isinstance(elem, CheckboxGrid):
            return [random_subset(elem.options, nonempty=elem.required) for _ in range(n)]
        opts = elem.options
        if not elem.required:
            opts = opts + [Value.EMPTY]
        return [random.choice(opts) for _ in range(n)]

    # text inputs / Date / DateTime / Time / Duration
    raise NotImplementedError(f'Cannot choose a random value for {elem._type_str()}')


_element_mapping = {getattr(ElementType, el_type.__name__.upper()): el_type for el_type in [
    Short, Paragraph,
    Radio, Dropdown, Checkboxes, Scale,
    Comment, Page, Image, Video,
]}


def parse(elem):
    el_type = ElementType(elem[Element.Index.TYPE])
    if el_type is ElementType.GRID:
        cls = CheckboxGrid if Grid.parse_multichoice(elem) else RadioGrid
    elif el_type is ElementType.DATE:
        cls = DateTime if DateElement.parse_time_flag(elem) else Date
    elif el_type is ElementType.TIME:
        cls = Duration if TimeElement.parse_duration_flag(elem) else Time
    else:
        cls = _element_mapping[el_type]
    return cls.parse(elem)
