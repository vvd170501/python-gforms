def invalid_type(value):
    return TypeError(f'Invalid argument type ({type(value).__name__})')


class ParseError(Exception):
    def __init__(self, form):
        super().__init__()
        self.form = form

    def __str__(self):
        return f'Cannot parse form with URL {self.form.url}'


class ClosedForm(ParseError):
    def __str__(self):
        return f'Form "{self.form.title}" is closed'


class ValidationError(Exception):
    def __init__(self, *args, **kwargs):
        pass


class ElementError(ValidationError):
    def __init__(self, elem, index=0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.elem = elem
        self.index = index

    def __str__(self):
        return f'Invalid value(s) in "{self.elem.name}"'


class InvalidChoice(ElementError, ValueError):
    def __init__(self, elem, value, *args, **kwargs):
        super().__init__(elem, *args, **kwargs)
        self.value = value

    def __str__(self):
        return f'Invalid choice in "{self.elem.name}" ({self.value})'


class MultipleValues(ElementError):
    def __str__(self):
        return f'Multiple values are not allowed in "{self.elem.name}"'


class RequiredElement(ElementError):
    def __str__(self):
        return f'An entry in required element "{self.elem.name}" is empty'


class EmptyOther(RequiredElement):
    def __str__(self):
        return f'Empty "Other" value in required element "{self.elem.name}"'


class DuplicateOther(ElementError):
    def __init__(self, elem, val1, val2, *args, **kwargs):
        super().__init__(elem, *args, **kwargs)
        self.val1 = val1
        self.val2 = val2

    def __str__(self):
        return f'Duplicate "Other" values in "{self.elem.name}" ("{self.val1}" and "{self.val2}")'


class RowError(ElementError):
    @property
    def _row(self):
        return self.elem.rows[self.index]


class RequiredRow(RequiredElement, RowError):
    def __str__(self):
        return f'A row ("{self._row}") in required element "{self.elem.name}" is empty'


class MultipleRowValues(MultipleValues, RowError):
    def __str__(self):
        return f'Multiple values are not allowed in "{self.elem.name}" (row "{self._row}")'


class InvalidDuration(ElementError, ValueError):
    def __init__(self, elem, value, *args, **kwargs):
        super().__init__(elem, *args, **kwargs)
        self.value = value

    def __str__(self):
        return f'Duration value ({self.value.total_seconds()} seconds) is out of range: ' \
               f'value should be positive and less than 73 hours '


class InfiniteLoop(ValidationError):
    def __init__(self, form):
        super().__init__(form)

    def __str__(self):
        return 'Chosen input values lead to an infinite loop'
