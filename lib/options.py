from .util import Action


class Option:
    class Index:
        VALUE = 0

    @classmethod
    def parse(cls, raw):
        if len(raw) == 1:  # scale or grid
            return SimpleOption(raw)
        if raw[SelectOption.Index.ACTION] is None:
            return SelectOption(raw)
        return ActionOption(raw)

    def __init__(self, raw):
        self.value = raw[self.Index.VALUE]

    def __str__(self):
        return self.value

    def to_str(self, indent=0):
        return self.value


class SimpleOption(Option):
    pass


class SelectOption(Option):
    class Index(Option.Index):
        ACTION = 2
        OTHER = 4
        IMAGE = 5  # not implemented

    def __init__(self, raw):
        super().__init__(raw)
        self.other = raw[self.Index.OTHER]

    def to_str(self, indent=0):
        if self.other:
            return 'Other'
        return self.value


class ActionOption(SelectOption):
    def __init__(self, raw):
        super().__init__(raw)
        self._action = raw[self.Index.ACTION]
        self.next_page = None

    def to_str(self, indent=0):
        from .elements import Page
        s = super().to_str(indent)
        if self.next_page is Page.SUBMIT():
            return f'{s} -> Submit'
        if self.next_page is None:
            return f'{s} -> Ignored'
        return f'{s} -> Go to Page {self.next_page.index + 1}'

    def _resolve_action(self, next_page, mapping):
        if next_page is None:
            return
        if self._action == Action.NEXT:
            self.next_page = next_page
        else:
            self.next_page = mapping[self._action]
