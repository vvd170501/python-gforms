import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import TYPE_CHECKING, List, cast
from warnings import warn

from .errors import SameColumn, UnknownValidator, InvalidText, InvalidArguments, InvalidChoiceCount
from .util import EMAIL_REGEX, URL_REGEX, DefaultEnum, ArgEnum, list_get

if TYPE_CHECKING:
    from elements import Checkboxes


class Subtype(DefaultEnum, ArgEnum):
    # Add UNKNOWN dynamically?

    @property
    def argnum(self):
        return self.arg[0]

    def descr(self, args):
        if args is None:
            return self.arg[1]
        return self.arg[1].format(*args)


class Validator(ABC):
    """A validator for a form element.

    Attributes:
        type: A member of cls.Type, indicating the validator's type.
        subtype: The validator's subtype.
        args: Validator arguments.
        error_msg: Custom error message, if it exists.
        bad_args: A boolean
            indicating if the arguments could not be parsed correctly.
    """

    class Type(DefaultEnum, ArgEnum):
        # Add UNKNOWN dynamically?

        @property
        def subtype_class(self):
            return self.arg

    class _Index:
        TYPE = 0
        SUBTYPE = 1
        ARGS_OR_MSG = 2

    @classmethod
    def parse(cls, val):
        """Creates a Validator from its JSON representation."""
        if len(val) <= cls._Index.SUBTYPE:
            return cls._unknown_validator(val)
        type_ = cls.Type(val[cls._Index.TYPE])
        if type_ is cls.Type.UNKNOWN:
            return cls._unknown_validator(val)
        subtype_cls = type_.subtype_class
        subtype = subtype_cls(val[cls._Index.SUBTYPE])
        if subtype is subtype_cls.UNKNOWN:
            return cls._unknown_validator(val, type_, subtype)

        argnum = subtype.argnum
        msg_index = cls._Index.ARGS_OR_MSG
        args = None
        if argnum > 0:
            args = list_get(val, cls._Index.ARGS_OR_MSG, None)
            msg_index += 1
        # If args are needed but not found, msg_index will not be increased. msg is not used -> ok
        msg = list_get(val, msg_index, None)
        args, valid_args = cls._parse_args(args, type_, subtype, argnum)
        if not valid_args:
            warn(InvalidArguments(cls, type_, subtype, args))
        return cls(type_, subtype, args, not valid_args, msg)

    def __init__(self, type_, subtype, args, bad_args, error_msg):
        self.type = type_
        self.subtype: Subtype = subtype
        self.args = args
        self.error_msg = error_msg
        self.bad_args = bad_args

    def validate(self, elem):
        """Validates the element's value."""
        if self.has_unknown_type() or self.bad_args:
            return
        self._validate(elem, elem._values)

    def has_unknown_type(self):
        return self.type is self.Type.UNKNOWN or self.subtype is self.type.subtype_class.UNKNOWN

    def to_str(self):
        if self.has_unknown_type():
            return 'Unknown validator'
        return f'{self._descr()}'

    @classmethod
    def _unknown_validator(cls, val, type_=None, subtype=None):
        warn(UnknownValidator(cls, val))
        return cls(type_ or cls.Type.UNKNOWN, subtype or cls.Type.UNKNOWN,
                   args=None, bad_args=False, error_msg=None)  # only type is important

    @classmethod
    def _parse_args(cls, args, type_, subtype, argnum):
        """
        Convert arguments to needed type. All args are received as strings
        Return value: converted args and a value indicating if conversion was successful
        """
        if args is None:
            return None, not argnum  # Error if args are required, but not found
        if not isinstance(args, list):
            return args, False  # e.g. new argnum is zero -> we get err_msg instead of args
        if len(args) != argnum:
            return args, False
        return cls._parse_arg_list(args, type_, subtype)

    @classmethod
    @abstractmethod
    def _parse_arg_list(cls, args, type_, subtype):
        raise NotImplementedError()

    def _descr(self):
        return self.subtype.descr(self.args)

    @abstractmethod
    def _validate(self, elem, values: List[List[str]]):
        raise NotImplementedError()


class NumberTypes(Subtype):
    UNKNOWN = (-1, (0, 'Unknown validator'))
    GT = (1, (1, 'Number > {}'))
    GE = (2, (1, 'Number >= {}'))
    LT = (3, (1, 'Number < {}'))
    LE = (4, (1, 'Number <= {}'))
    EQ = (5, (1, 'Number == {}'))
    NE = (6, (1, 'Number != {}'))
    RANGE = (7, (2, 'Number in range [{}, {}]'))
    NOT_RANGE = (8, (2, 'Number not in range [{}, {}]'))
    IS_NUMBER = (9, (0, 'A number'))
    IS_INT = (10, (0, 'An integer'))


class TextTypes(Subtype):
    UNKNOWN = (-1, (0, 'Unknown validator'))
    CONTAINS = (100, (1, 'Must contain "{}"'))
    NOT_CONTAINS = (101, (1, 'Must not contain "{}"'))
    EMAIL = (102, (0, 'An E-mail address'))
    URL = (103, (0, 'URL'))


class LengthTypes(Subtype):
    UNKNOWN = (-1, (0, 'Unknown validator'))
    MAX_LENGTH = (202, (1, 'Max {} characters'))
    MIN_LENGTH = (203, (1, 'Min {} characters'))


class RegexTypes(Subtype):
    UNKNOWN = (-1, (0, 'Unknown validator'))
    CONTAINS = (299, (1, 'Must contain regex "{}"'))
    NOT_CONTAINS = (300, (1, 'Must not contain regex "{}"'))
    MATCHES = (301, (1, 'Must match regex "{}"'))
    NOT_MATCHES = (302, (1, 'Must not match regex "{}"'))

    def descr(self, args):
        if args is None:
            return self.arg[1]
        return self.arg[1].format(*(arg.pattern for arg in args))


class TextValidator(Validator):
    class Type(Validator.Type):
        UNKNOWN = (-1, None)
        NUMBER = (1, NumberTypes)
        TEXT = (2, TextTypes)
        REGEX = (4, RegexTypes)
        LENGTH = (6, LengthTypes)

    @classmethod
    def _parse_arg_list(cls, args, type_, subtype):
        if type_ is cls.Type.TEXT:
            return args, True  # only string args
        if type_ is cls.Type.LENGTH:
            try:
                return [int(arg) for arg in args], True
            except ValueError:
                return args, False
        if type_ is cls.Type.NUMBER:
            try:
                args = [float(arg) for arg in args]
                for i in range(len(args)):
                    if args[i].is_integer():
                        args[i] = int(args[i])
                return args, True
            except ValueError:
                return args, False
        if type_ is cls.Type.REGEX:
            try:
                return [re.compile(arg) for arg in args], True
            except re.error:
                return args, False

    def _descr(self):
        return 'Allowed values: ' + super()._descr()

    def _validate(self, elem, values: List[List[str]]):
        if not values[0]:  # empty element
            return
        value = values[0][0]
        if self.type is self.Type.NUMBER:
            is_ok = self._validate_number(value)
        elif self.type is self.Type.TEXT:
            is_ok = self._validate_text(value)
        elif self.type is self.Type.LENGTH:
            is_ok = self._validate_length(value)
        elif self.type is self.Type.REGEX:
            is_ok = self._validate_regex(value)
        else:
            raise NotImplementedError()
        if not is_ok:
            descr = self._descr()
            if self.error_msg:
                descr = f'{self.error_msg} ({descr})'
            raise InvalidText(elem, value, details=descr)

    def _validate_number(self, val):
        if self.subtype is NumberTypes.IS_INT:
            try:
                _ = int(val)
                return True
            except ValueError:
                return False
        try:
            val = float(val)
        except ValueError:
            return False

        if self.subtype is NumberTypes.IS_NUMBER:
            # NOTE will return True for "NaN", "Inf" and "Infinity".
            # JS validator accepts only the last one.
            # It was not tested if these values pass the server-side validation
            return True
        arg = self.args[0]
        if self.subtype is NumberTypes.GT:
            return val > arg
        if self.subtype is NumberTypes.GE:
            return val >= arg
        if self.subtype is NumberTypes.LT:
            return val < arg
        if self.subtype is NumberTypes.LE:
            return val <= arg
        if self.subtype is NumberTypes.EQ:
            # if arg == 2.0, "1.99..9" will pass validation.
            # It's ok, as long as the value is accepted by server
            return val == arg
        if self.subtype is NumberTypes.NE:
            return val != arg
        if self.subtype is NumberTypes.RANGE:
            # The first arg can be greater than the second. This is checked in TextInput.
            return self.args[0] <= val <= self.args[1]
        if self.subtype is NumberTypes.NOT_RANGE:
            # The first arg can be greater than the second, it's ok
            return val < min(self.args) or val > max(self.args)
        raise NotImplementedError()

    def _validate_text(self, val):
        if self.subtype is TextTypes.CONTAINS:
            return self.args[0] in val
        if self.subtype is TextTypes.NOT_CONTAINS:
            return self.args[0] not in val
        if self.subtype is TextTypes.EMAIL:
            return EMAIL_REGEX.match(val) is not None
        if self.subtype is TextTypes.URL:
            # couldn't find a regex / checking algorithm in page source
            # It seems that URLS are validaetd on the server side
            # (client performs only basic checks)
            return URL_REGEX.match(val) is not None
        raise NotImplementedError()

    def _validate_length(self, val):
        if self.subtype is LengthTypes.MIN_LENGTH:
            return len(val) >= self.args[0]
        if self.subtype is LengthTypes.MAX_LENGTH:
            return len(val) <= self.args[0]
        raise NotImplementedError()

    def _validate_regex(self, val):
        if self.subtype is RegexTypes.CONTAINS:
            return self.args[0].search(val) is not None
        if self.subtype is RegexTypes.NOT_CONTAINS:
            return self.args[0].search(val) is None
        if self.subtype is RegexTypes.MATCHES:
            return self.args[0].match(val) is not None
        if self.subtype is RegexTypes.NOT_MATCHES:
            return self.args[0].match(val) is None
        raise NotImplementedError()


class GridTypes(Subtype):
    UNKNOWN = (-1, (0, 'Unknown validator'))
    EXCLUSIVE_COLUMNS = (205, (0, 'Max 1 response per column'))


class GridValidator(Validator):
    class Type(Validator.Type):
        UNKNOWN = (-1, None)
        DEFAULT = (8, GridTypes)

    @classmethod
    def _parse_arg_list(cls, args, type_, subtype):
        # no args are needed.
        # This method will be called only if args is an empty list (is it possible?)
        return None, True

    def _validate(self, elem, values: List[List[str]]):
        if self.subtype is GridTypes.EXCLUSIVE_COLUMNS:
            cnt = Counter()
            for row in values:
                if row:
                    cnt.update(row)
                    col, count = max(cnt.items(), key=lambda x: x[1])
                    if count > 1:
                        raise SameColumn(elem, col)
        else:
            raise NotImplementedError()


class CheckboxTypes(Subtype):
    UNKNOWN = (-1, (0, 'Unknown validator'))
    AT_LEAST = (200, (1, 'at least {} option(s)'))
    AT_MOST = (201, (1, 'at most {} option(s)'))
    EXACTLY = (204, (1, 'exactly {} option(s)'))


class CheckboxValidator(Validator):
    class Type(Validator.Type):
        UNKNOWN = (-1, None)
        DEFAULT = (7, CheckboxTypes)

    @classmethod
    def _parse_arg_list(cls, args, type_, subtype):
        try:
            return [int(arg) for arg in args], True
        except ValueError:
            return args, False

    def _validate(self, elem, values: List[List[str]]):
        required = self.args[0]
        cnt = len(values[0])
        if cast('Checkboxes', elem)._other_value is not None:
            cnt += 1
        if self.subtype is CheckboxTypes.AT_LEAST:
            is_ok = cnt >= required
        elif self.subtype is CheckboxTypes.AT_MOST:
            is_ok = cnt <= required
        elif self.subtype is CheckboxTypes.EXACTLY:
            is_ok = cnt == required
        else:
            raise NotImplementedError()
        if not is_ok:
            raise InvalidChoiceCount(elem, cnt)

    def _descr(self):
        return 'Select ' + super()._descr()
