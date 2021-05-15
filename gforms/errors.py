from abc import ABC, abstractmethod


class FormError(Exception, ABC):
    """Base error class"""
    def __init__(self, *args, details=None, **kwargs):
        super().__init__()
        self.details = details

    @abstractmethod
    def _message(self):
        raise NotImplementedError()

    def __str__(self):
        message = self._message()
        if self.details:
            message += f' ({self.details})'
        return message


class ParseError(FormError):
    def __init__(self, form, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.form = form

    def _message(self):
        return f'Cannot parse form with URL {self.form.url}'


class ClosedForm(ParseError):
    def _message(self):
        return f'Form "{self.form.title}" is closed'


class ValidationError(FormError, ValueError):
    pass


class ElementError(FormError):
    def __init__(self, elem, *args, index=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.elem = elem
        self.index = index


class IncompatibleType(ElementError, TypeError):
    def __init__(self, elem, value, *args, **kwargs):
        super().__init__(elem, *args, **kwargs)
        self.value = value

    def _message(self):
        return 'Unsupported argument type '\
               f'(element: "{self.elem.name}", argument: {repr(self.value)})'


class IncompatibleValue(ElementError, ValueError):  # not the best name
    def __init__(self, elem, value, *args, **kwargs):
        super().__init__(elem, *args, **kwargs)
        self.value = value

    def _message(self):
        return 'Cannot fill an entry with the chosen value '\
               f'(element: "{self.elem.name}", value: {repr(self.value)})'


class InvalidValue(ElementError, ValidationError):
    def __init__(self, elem, value, *args, **kwargs):
        super().__init__(elem, *args, **kwargs)
        self.value = value


class InvalidText(InvalidValue):
    def _message(self):
        return f'Invalid text input in "{self.elem.name}" ({self.value})'


class InvalidChoice(InvalidValue):
    def _message(self):
        return f'Invalid choice in "{self.elem.name}" ({self.value})'


class MultipleValues(ElementError, ValueError):
    def _message(self):
        return f'Multiple values are not allowed in "{self.elem.name}"'


class RequiredElement(ElementError, ValidationError):
    def _message(self):
        return f'An entry in required element "{self.elem.name}" is empty'


class EmptyOther(RequiredElement):
    def _message(self):
        return f'Empty "Other" value in required element "{self.elem.name}"'


class DuplicateOther(ElementError, ValueError):
    def __init__(self, elem, val1, val2, *args, **kwargs):
        super().__init__(elem, *args, **kwargs)
        self.val1 = val1
        self.val2 = val2

    def _message(self):
        return f'Duplicate "Other" values in "{self.elem.name}" ("{self.val1}" and "{self.val2}")'


class RowError(ElementError):
    @property
    def row(self):
        return self.elem.rows[self.index]


class RequiredRow(RequiredElement, RowError):
    def _message(self):
        return f'A row ("{self.row}") in required element "{self.elem.name}" is empty'


class MultipleRowValues(MultipleValues, RowError):
    def _message(self):
        return f'Multiple values are not allowed in "{self.elem.name}" (row "{self.row}")'


class InvalidDuration(InvalidValue):
    def _message(self):
        return f'Duration value ({self.value.total_seconds()} seconds) is out of range: ' \
               f'value should be positive and less than 73 hours '


class InfiniteLoop(FormError, ValueError):
    def __init__(self, form):
        super().__init__(form)

    def _message(self):
        return 'Chosen input values lead to an infinite loop'
