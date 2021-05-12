class ValidationError(ValueError):
    pass


class ElementError(ValidationError):
    def __init__(self, elem):
        super().__init__()
        self.elem = elem

    def __str__(self):
        return f'Invalid value in "{self.elem.name}"'


class InvalidValue(ElementError):
    def __init__(self, elem, value):
        super().__init__(elem)
        self.value = value

    def __str__(self):
        return f'Invalid value in "{self.elem.name}" ({self.value})'


class MultipleValues(ElementError):
    def __str__(self):
        return f'Multiple values are not allowed in "{self.elem.name}")'


class DuplicateOther(ElementError):
    def __str__(self):
        return f'Duplicate "Other" values in "{self.elem.name}"'


class RequiredElement(ElementError):
    def __str__(self):
        return f'Required element "{self.elem.name}" is empty'


class RowError(ElementError):
    def __init__(self, elem, row):
        super().__init__(elem)
        self.row = row


class RequiredRow(RowError, RequiredElement):
    def __str__(self):
        return f'Required element "{self.elem.name}" (row "{self.row}") is empty'


class MultipleRowValues(RowError, MultipleValues):
    def __str__(self):
        return f'Multiple values are not allowed in "{self.elem.name}" (row "{self.row}")'


class InfiniteLoop(ValidationError):
    def __init__(self, form):
        super().__init__(form)

    def __str__(self):
        return 'Chosen input values lead to an infinite loop'
