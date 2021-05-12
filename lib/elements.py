import random
from enum import Enum, auto
from typing import List, Literal, Union

from .errors import DuplicateOther, InvalidValue, MultipleRowValues, MultipleValues, \
                    RequiredElement, RequiredRow
from .options import ActionOption, Option
from .util import Action, add_indent, random_subset, SEP_WIDTH


class Value(Enum):
    DEFAULT = auto()
    EMPTY = auto()


TextValue = str
ChoiceValue = Union[Option, str]
MultiChoiceValue = Union[ChoiceValue, List[ChoiceValue]]
ScaleValue = Union[ChoiceValue, int]

EmptyValue = Literal[Value.EMPTY]
GridValue = List[Union[MultiChoiceValue, EmptyValue]]  # choice(s) for each row
ElemValue = Union[TextValue, ScaleValue, ChoiceValue, MultiChoiceValue, GridValue]

CallbackRetval = Union[ElemValue, Value]


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


class Element:
    class Index:
        ID = 0
        NAME = 1
        DESCRIPTION = 2
        TYPE = 3

    _mapping = None

    @classmethod
    def parse(cls, elem):
        if cls._mapping is None:  # first call
            cls._mapping = {el_type: globals()[el_type.name.title()] for el_type in ElementType}
        el_type = ElementType(elem[cls.Index.TYPE])
        return cls._mapping[el_type](elem)

    def __init__(self, elem):
        self.id = elem[self.Index.ID]
        self.name = elem[self.Index.NAME]
        self.description = elem[self.Index.DESCRIPTION]  # may be None
        self.type = ElementType(elem[self.Index.TYPE])

    def to_str(self, indent=0, **kwargs):
        s = f'{self.type.name.title()}: {self.name}'
        if self.description:
            s = f'{s}\n{self.description}'
        return s


class MediaElement(Element):
    # elem[6][0] - image url (?)
    def to_str(self, indent=0, **kwargs):
        tp = self.type.name.title()
        if self.name:
            return f'{tp}: {self.name}'
        return tp


class InputElement(Element):
    class Index(Element.Index):
        VALUE = 4
        ENTRY_ID = 0
        OPTIONS = 1
        REQUIRED = 2

    def __init__(self, elem):
        super().__init__(elem)
        value = elem[self.Index.VALUE][0]
        self.entry_id = value[self.Index.ENTRY_ID]
        self.required = value[self.Index.REQUIRED]
        self.value = Value.EMPTY

    def set_value(self, value: Union[ElemValue, EmptyValue]):
        if value is Value.EMPTY and self.required:
            raise RequiredElement(self)
        self.value = value

    def payload(self):
        if self.value is Value.EMPTY:
            return {}
        return {self._submit_id(): self.value}

    def to_str(self, indent=0, include_answer=False):
        s = f'{self.type.name.title()}: {self.name}'
        if self.required:
            s += '*'
        if self.description:
            s = f'{s}\n{self.description}'
        if include_answer:
            s = self._with_answer(s)
        return s

    def _with_answer(self, s):
        if self.value is Value.EMPTY:
            val = 'EMPTY'
        else:
            val = f'"{self.value}"'
        return f'{s}\n> {val}'

    def _submit_id(self):
        return f'entry.{self.entry_id}'


class TextInputElement(InputElement):
    def set_value(self, value: Union[TextValue, EmptyValue]):
        super().set_value(value)


# TODO refactor class hierarchy?
class ChoiceInputElement(InputElement):
    def __init__(self, elem):
        super().__init__(elem)

        value = elem[self.Index.VALUE][0]
        self.options = []
        self.other_option = None
        for opt in value[self.Index.OPTIONS]:
            option = Option.parse(opt)
            if getattr(option, 'other', False):
                self.other_option = option
            else:
                self.options.append(option)

        self.other_value = Value.EMPTY

    def set_value(self, choices: Union[MultiChoiceValue, EmptyValue]):
        self.other_value = Value.EMPTY
        all_choices = self._canonical_form(choices)
        if all_choices is Value.EMPTY:
            if self.required:
                raise RequiredElement(self)
            self.value = Value.EMPTY
            return

        choices = []
        available = {opt.value for opt in self.options}
        for i, choice in enumerate(all_choices):
            is_other = False
            if isinstance(choice, Option):
                # assuming choice is in self.options or choice == self.other_option
                is_other = choice.other
                choice = choice.value
            else:
                is_other = choice not in available

            if is_other:
                if self.other_option is None:
                    raise InvalidValue(self, choice)
                if self.other_value is not Value.EMPTY:
                    raise DuplicateOther(self)
                self.other_value = choice
            else:
                choices.append(choice)

        if not choices:
            choices = Value.EMPTY
        self.value = choices

    def payload(self):
        if self.value is Value.EMPTY and self.other_value is Value.EMPTY:
            return {}
        main_key = self._submit_id()
        payload = {main_key: []}
        if self.value is not Value.EMPTY:
            payload[main_key] += self.value
        if self.other_value is not Value.EMPTY:
            payload[main_key].append('__other_option__')
            other_key = main_key + '.other_option_response'
            payload[other_key] = self.other_value
        return payload

    def to_str(self, indent=0, include_answer=False):
        s = super().to_str(indent)
        s = '\n'.join([s] + [add_indent(f'- {opt.to_str()}', indent) for opt in self.options])
        if include_answer:
            s = self._with_answer(s)
        return s

    @staticmethod
    def _canonical_form(choices):
        if choices is Value.EMPTY:
            return Value.EMPTY

        if isinstance(choices, list):
            if not choices:
                return Value.EMPTY
            return choices[:]
        return [choices]

    def _with_answer(self, s):
        if self.value is Value.EMPTY:
            val = 'EMPTY'
        else:
            val = ', '.join(f'"{choice}"' for choice in self.value)
        return f'{s}\n> {val}'


class ActChoiceInputElement(ChoiceInputElement):
    """ChoiceInputElement with optional actions based on choice"""
    def __init__(self, elem):
        super().__init__(elem)
        self.next_page = None

    def set_value(self, choice: Union[ChoiceValue, EmptyValue]):
        super().set_value(choice)

        if self.value is not Value.EMPTY and \
                (self.other_value is not Value.EMPTY or len(self.value) > 1):
            raise MultipleValues(self)

        self.next_page = None

        if isinstance(choice, ActionOption):
            self.next_page = choice.next_page
        elif isinstance(choice, str) and isinstance(self.options[0], ActionOption):
            if self.other_value is not Value.EMPTY:
                self.next_page = self.other_option.next_page
                return
            for opt in self.options:
                if opt.value == choice:
                    self.next_page = opt.next_page
                    return

    def to_str(self, indent=0, include_answer=False):
        s = super().to_str(indent, include_answer)
        if include_answer and self.value is not Value.EMPTY and self.next_page is not None:
            if self.next_page is Page.SUBMIT():
                s = f'{s}\nGo to SUBMIT'
            else:
                s = f'{s}\nGo to page {self.next_page.index + 1}'
        return s

    def _resolve_actions(self, next_page, mapping):
        for option in self.options:
            if isinstance(option, ActionOption):
                option._resolve_action(next_page, mapping)


class Comment(Element):
    pass


class Image(MediaElement):
    pass


class Video(MediaElement):
    pass


class Short(TextInputElement):
    pass


class Paragraph(TextInputElement):
    pass


class Radio(ActChoiceInputElement):
    pass


class Dropdown(ActChoiceInputElement):
    pass


class Checkboxes(ChoiceInputElement):
    pass


class Scale(ChoiceInputElement):
    class Index(ChoiceInputElement.Index):
        LABELS = 3

    def __init__(self, elem):
        super().__init__(elem)
        value = elem[self.Index.VALUE][0]
        labels = value[self.Index.LABELS]
        self.low, self.high = labels

    def set_value(self, value: Union[ScaleValue, EmptyValue]):
        if isinstance(value, int):
            value = str(value)
        super().set_value(value)
        if self.value is not Value.EMPTY and len(self.value) > 1:
            raise MultipleValues(self)

    def to_str(self, indent=0, include_answer=False):
        s = super(ChoiceInputElement, self).to_str(indent)
        values = f'{self.options[0].to_str(indent)} - {self.options[-1].to_str(indent)}'
        if self.low:
            values = f'({self.low}) {values}'
        if self.high:
            values = f'{values} ({self.high})'
        s = f'{s}\n{add_indent(values, indent)}'
        if include_answer:
            s = self._with_answer(s)
        return s


class Grid(ChoiceInputElement):
    class Index(InputElement.Index):
        ROW_NAME = 3
        MULTICHOICE = 11

    def __init__(self, elem):
        super().__init__(elem)
        value = elem[self.Index.VALUE]
        self.entry_ids = [row[self.Index.ENTRY_ID] for row in value]
        self.rows = [row[self.Index.ROW_NAME][0] for row in value]
        self.multichoice = value[0][self.Index.MULTICHOICE][0]

    def set_value(self, choices: Union[GridValue, EmptyValue]):
        if choices is Value.EMPTY or not choices:
            if self.required:
                raise RequiredElement(self)
            self.value = Value.EMPTY
            return

        choices = choices[:]

        for i, row in enumerate(choices):
            row = choices[i] = self._canonical_form(row)
            if row is Value.EMPTY:
                if self.required:
                    raise RequiredRow(self, row)
                continue
            if len(row) > 1 and not self.multichoice:
                raise MultipleRowValues(self, row)
            for j, choice in enumerate(row):
                if isinstance(choice, Option):
                    row[j] = choice.value
        if all(row is Value.EMPTY for row in choices):
            self.value = Value.EMPTY
        else:
            self.value = choices

    def payload(self):
        if self.value is Value.EMPTY:
            return {}
        payload = {}
        for submit_id, choices in zip(self._submit_ids(), self.value):
            if choices is not Value.EMPTY:
                payload[submit_id] = choices
        return payload

    def to_str(self, indent=0, include_answer=False):
        tp = 'CheckboxGrid' if self.multichoice else 'RadioGrid'
        s = f'{tp}: {self.name}'
        if self.required:
            s += '*'
        if self.description:
            s = f'{s}\n{self.description}'

        value = '\n'.join(
            ['  ' + ' | '.join([opt.to_str() for opt in self.options])] +
            [f'- {row}' for row in self.rows]
        )
        s = f'{s}\n{add_indent(value, indent)}'
        if include_answer:
            s = self._with_answer(s)
        return s

    def _submit_ids(self):
        return [f'entry.{eid}' for eid in self.entry_ids]

    def _with_answer(self, s):
        def row_fmt(row):
            if row is Value.EMPTY:
                return 'EMPTY'
            return ', '.join(f'"{choice}"' for choice in row)
        if self.value is Value.EMPTY:
            val = 'EMPTY'
        else:
            val = [f'> {row_fmt(row)}' for row in self.value]
        return '\n'.join([s] + val)


class Page(Element):
    _SUBMIT = None

    @classmethod
    def SUBMIT(cls):
        if cls._SUBMIT is None:
            instance = super().__new__(cls)
            instance.__init__(Action.SUBMIT, None)
            instance.id = Action.SUBMIT
            cls._SUBMIT = instance
        return cls._SUBMIT

    class Index(Element.Index):
        ACTION = 5

    def __init__(self, index,  elem=None):
        if elem is None:
            self.name = None
            self.description = None
            self.type = ElementType.PAGE
            self.id = Action.FIRST
            self._prev_action = Action.NEXT
        else:
            super().__init__(elem)
            if len(elem) > self.Index.ACTION:
                self._prev_action = elem[self.Index.ACTION]
            else:
                self._prev_action = Action.NEXT
        self.index = index
        self.elements = []
        self._next_page = None
        self._has_default_next_page = True

    def append(self, elem):
        self.elements.append(elem)

    def next_page(self):
        if self._next_page is None:
            return None

        next_page = self._next_page
        for elem in self.elements:
            if isinstance(elem, ActChoiceInputElement) and elem.next_page is not None:
                next_page = elem.next_page
        return next_page

    def to_str(self, indent=0, include_answer=False):
        SEPARATOR = '—' * (SEP_WIDTH - indent)
        title = f'Page {self.index + 1}:'
        if self.name:
            title = f'{title} {self.name}'
        if self.description:
            title = f'{title}\n{self.description}'
        if not self._has_default_next_page:
            if self._next_page is Page.SUBMIT():
                title = f'{title} -> Submit'
            else:
                title = f'{title} -> Page {self._next_page.index + 1}'
        if not self.elements:
            return title
        return '\n'.join(
            [title] +
            [
                SEPARATOR + '\n' +
                add_indent(elem.to_str(indent=indent, include_answer=include_answer), indent)
                for elem in self.elements
            ]
        )

    def _resolve_actions(self, next_page, mapping):
        for elem in self.elements:
            if isinstance(elem, ActChoiceInputElement):
                elem._resolve_actions(next_page, mapping)

        if next_page is None:
            return
        if next_page._prev_action == Action.NEXT:
            self._next_page = next_page
        else:
            self._next_page = mapping[next_page._prev_action]
            self._has_default_next_page = False


class Date(InputElement):
    # TODO add implementation
    "entry.{id}_year"  # optional
    "entry.{id}_month"
    "entry.{id}_day"
    "entry.{id}_hour"  # optional
    "entry.{id}_minute"  # optional
    pass


class Time(InputElement):
    # TODO add implementation
    "entry.{id}_hour"
    "entry.{id}_minute"
    "entry.{id}_second"  # optional
    pass


def default_callback(elem: InputElement, page_index, elem_index) -> Union[ElemValue, EmptyValue]:
    if isinstance(elem, Scale) or isinstance(elem, Dropdown):
        return random.choice(elem.options)
    if isinstance(elem, Radio):
        # Don't auto-choose "Other"
        return random.choice(elem.options)

    # Example: allow "Other"
#       if elem.other_option is not None:
#           opt = random.choice(elem.options + [elem.other_option])
#           if opt.other:
#               # return 'Sample text'  # another alternative
#               opt.value = 'Sample text'
#           return opt

    if isinstance(elem, Checkboxes):
        # Don't auto-choose "Other"
        return random_subset(elem.options, nonempty=elem.required)

    if isinstance(elem, Grid):
        n = len(elem.rows)
        if elem.multichoice:
            return [random_subset(elem.options, nonempty=elem.required) for i in range(n)]
        opts = elem.options
        if not elem.required:
            opts = opts + [Value.EMPTY]
        return [random.choice(opts) for i in range(n)]

    print(f'Input value for {elem.type.name.title()}: "{elem.name}"'
          f' (Page {page_index + 1}, Element {elem_index + 1})')
    return input()
