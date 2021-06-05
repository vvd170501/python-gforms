from .util import list_get


class Option:
    """A choice option for a ChoiceInput.

    Attributes:
        value: The option's value.
        other: Whether or not this option is the "Other" option.
    """

    class _Index:
        VALUE = 0
        ACTION = 2
        OTHER = 4
        IMAGE = 5  # not implemented

    @classmethod
    def parse(cls, option):
        """Creates an Option from its JSON representation.

        This method should not be called directly,, use options.parse instead.
        """
        return cls(**cls._parse(option))

    @classmethod
    def _parse(cls, option):
        return {
            'value': option[cls._Index.VALUE] or '',
            'other': bool(list_get(option, cls._Index.OTHER, False)),
        }

    def __init__(self, *, value, other):
        self.value = value
        self.other = other

    def to_str(self, indent=0, with_value=None):
        """Returns a text representation of the option.

        For args description, see Form.to_str.
        """
        if self.other:
            if with_value is not None:
                return f'Other: "{with_value}"'
            return 'Other'
        return self.value


class ActionOption(Option):
    """An option, which, when chosen, may lead to a different page.

    Attributes:
        next_page: The next page for this option.
    """

    @classmethod
    def _parse(cls, option):
        res = super()._parse(option)
        res.update({
            'action': option[cls._Index.ACTION],
        })
        return res

    def __init__(self, *, action, **kwargs):
        super().__init__(**kwargs)
        self._action = action
        self.next_page = None

    def to_str(self, indent=0, with_value=None):
        """See base class."""
        from .elements import Page
        s = super().to_str(indent, with_value)
        if self.next_page is Page.SUBMIT:
            return f'{s} -> Submit'
        if self.next_page is None:
            return f'{s} -> Ignored'
        return f'{s} -> Go to Page {self.next_page.index + 1}'

    def _resolve_action(self, next_page, mapping):
        from .elements import _Action
        if next_page is None:
            return
        if self._action == _Action.NEXT:
            self.next_page = next_page
        else:
            self.next_page = mapping[self._action]


def parse(option):
    """Creates an Option of the right type from its JSON representation."""
    if len(option) > Option._Index.ACTION and option[Option._Index.ACTION] is not None:
        return ActionOption.parse(option)
    return Option.parse(option)
