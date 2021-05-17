class Option:
    class Index:
        VALUE = 0
        ACTION = 2
        OTHER = 4
        IMAGE = 5  # not implemented

    @classmethod
    def parse(cls, option):
        return cls(**cls._parse(option))

    @classmethod
    def _parse(cls, option):
        res = {
            'value': option[cls.Index.VALUE],
            'other': False,
        }
        # len(option) == 1 for Scale options or if the element has only one option with no actions
        if len(option) > cls.Index.OTHER:
            res.update({
                'other': bool(option[cls.Index.OTHER]),
                'value': res['value'] or ''
            })
        return res

    def __init__(self, *, value, other):
        self.value = value
        self.other = other

    def to_str(self, indent=0, with_value=None):
        if self.other:
            if with_value is not None:
                return f'Other: "{with_value}"'
            return 'Other'
        return self.value


class ActionOption(Option):
    @classmethod
    def _parse(cls, option):
        res = super()._parse(option)
        res.update({
            'action': option[cls.Index.ACTION],
        })
        return res

    def __init__(self, *, action, **kwargs):
        super().__init__(**kwargs)
        self._action = action
        self.next_page = None

    def to_str(self, indent=0, with_value=None):
        from .elements import Page
        s = super().to_str(indent, with_value)
        if self.next_page is Page.SUBMIT:
            return f'{s} -> Submit'
        if self.next_page is None:
            return f'{s} -> Ignored'
        return f'{s} -> Go to Page {self.next_page.index + 1}'

    def resolve_action(self, next_page, mapping):
        from .elements import Action
        if next_page is None:
            return
        if self._action == Action.NEXT:
            self.next_page = next_page
        else:
            self.next_page = mapping[self._action]


def parse(option):
    if len(option) > Option.Index.ACTION and option[Option.Index.ACTION] is not None:
        return ActionOption.parse(option)
    return Option.parse(option)
