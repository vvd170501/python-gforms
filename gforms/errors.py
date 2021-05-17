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


class ElementError(FormError):
    def __init__(self, elem, *args, index=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.elem = elem
        self.index = index


class InfiniteLoop(FormError, ValueError):
    def __init__(self, form):
        super().__init__(form)

    def _message(self):
        return 'Chosen input values lead to an infinite loop'


class RowError(ElementError):
    @property
    def row(self):
        return self.elem.rows[self.index]


class ValidationError(FormError, ValueError):
    pass


class InvalidValue(ElementError, ValidationError):
    def __init__(self, elem, value, *args, **kwargs):
        super().__init__(elem, *args, **kwargs)
        self.value = value


# The following errors may be raised from InputElement.set_value

class ElementTypeError(ElementError, TypeError):
    def __init__(self, elem, value, *args, **kwargs):
        super().__init__(elem, *args, **kwargs)
        self.value = value

    def _message(self):
        return 'Unsupported argument type' \
               f' (element: "{self.elem.name}", argument: {repr(self.value)})'


class ElementValueError(ElementError, ValueError):  # not the best name
    def __init__(self, elem, value, *args, **kwargs):
        super().__init__(elem, *args, **kwargs)
        self.value = value

    def _message(self):
        return 'Cannot fill an entry with the chosen value' \
               f' (element: "{self.elem.name}", value: {repr(self.value)})'


class InvalidChoice(ElementValueError):
    def _message(self):
        return f'Invalid choice in "{self.elem.name}" ({repr(self.value)})'


class DuplicateOther(ElementValueError):
    def __init__(self, elem, value, value2, *args, **kwargs):
        super().__init__(elem, value, *args, **kwargs)
        self.value2 = value2

    def _message(self):
        return f'Duplicate "Other" values in "{self.elem.name}"' \
               f' ("{self.value}" and "{self.value2}")'


class RowTypeError(ElementTypeError, RowError):
    def _message(self):
        return 'Unsupported argument type' \
               f' (element: "{self.elem.name}", row {self.row}, argument: {repr(self.value)})'


class InvalidRowChoice(InvalidChoice, RowError):
    def _message(self):
        return f'Invalid choice in "{self.elem.name}" ({self.value}) (row {self.row})'


# The following errors may be raised from InputElement.validate

class RequiredElement(ElementError, ValidationError):
    def _message(self):
        return f'An entry in required element "{self.elem.name}" is empty'


class EmptyOther(RequiredElement):
    def _message(self):
        return f'Empty "Other" value in required element "{self.elem.name}"'


class RequiredRow(RequiredElement, RowError):
    def _message(self):
        return f'A row ("{self.row}") in required element "{self.elem.name}" is empty'


class InvalidText(InvalidValue):
    def _message(self):
        return f'Invalid text input in "{self.elem.name}" ("{self.value}")'


class InvalidDuration(InvalidValue):
    def _message(self):
        return f'Duration value ({self.value.total_seconds()} seconds) is out of range:' \
               ' value should be positive and less than 73 hours'


class ValidatorWarning(UserWarning):
    pass


class UnknownValidator(ValidatorWarning):
    def __init__(self, cls, value):
        super().__init__()
        self.cls = cls
        self.value = value

    def __str__(self):
        return f'Unknown validator type for {self.cls.__name__}: {repr(self.value)},' \
               ' this validator will allow any input'


class InvalidArguments(ValidatorWarning):
    def __init__(self, val_type, subtype, args):
        super().__init__()
        self.val_type = val_type
        self.subtype = subtype
        self.args = args

    def __str__(self):
        return 'Cannot convert arguments for a validator.' \
              f' Type: {self.val_type} ({self.subtype}), Arguments: {repr(self.args)}.' \
               ' Validator is disabled'


class SameColumn(InvalidValue):
    def __init__(self, elem, value=None, column=None, *args, **kwargs):
        super().__init__(elem, value, *args, **kwargs)
        self.column = column

    def _message(self):
        detail = f'("{self.column}") ' if self.column else ''
        return f'Same column {detail}is chosen in two or more rows of "{self.elem}".' \
               ' The choices must be unique'


class MisconfiguredGrid(SameColumn):
    def _message(self):
        return f'Impossible to fill grid "{self.elem}": all rows are required and the choices' \
               ' must be unique, but there are less columns than rows'
