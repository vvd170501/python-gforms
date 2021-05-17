import re
from collections import Counter
from enum import Enum, auto
from typing import List, Union
from warnings import warn

from .errors import MisconfiguredGrid, SameColumn, UnknownValidator, InvalidText, InvalidArguments
from .util import EMAIL_REGEX, URL_REGEX, DefaultEnum, ArgEnum


class _Subtype(DefaultEnum, ArgEnum):
    @property
    def argnum(self):
        return self.arg[0]

    def descr(self, args):
        if args is None:
            return self.arg[1]
        return self.arg[1].format(*args)


class NumberTypes(_Subtype):
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


class TextTypes(_Subtype):
    UNKNOWN = (-1, (0, 'Unknown validator'))
    CONTAINS = (100, (1, 'Must contain "{}"'))
    NOT_CONTAINS = (101, (1, 'Must not contain "{}"'))
    EMAIL = (102, (0, 'An E-mail address'))
    URL = (103, (0, 'URL'))


class LengthTypes(_Subtype):
    UNKNOWN = (-1, (0, 'Unknown validator'))
    MAX_LENGTH = (202, (1, 'Max length: {}'))
    MIN_LENGTH = (203, (1, 'Min length: {}'))


class RegexTypes(_Subtype):
    UNKNOWN = (-1, (0, 'Unknown validator'))
    CONTAINS = (299, (1, 'Must contain regex "{}"'))
    NOT_CONTAINS = (300, (1, 'Must not contain regex "{}"'))
    MATCHES = (301, (1, 'Must match regex "{}"'))
    NOT_MATCHES = (302, (1, 'Must not match regex "{}"'))

    def descr(self, args):
        if args is None:
            return self.arg[1]
        return self.arg[1].format(*(arg.pattern for arg in args))


Subtype = Union[NumberTypes, TextTypes, LengthTypes, RegexTypes]


class TextValidator:
    class Index:
        TYPE = 0
        SUBTYPE = 1
        ARGS_OR_MSG = 2

    class Type(DefaultEnum, ArgEnum):
        UNKNOWN = (-1, None)
        NUMBER = (1, NumberTypes)
        TEXT = (2, TextTypes)
        REGEX = (4, RegexTypes)
        LENGTH = (6, LengthTypes)

        @property
        def subtype_class(self):
            return self.arg

    @classmethod
    def parse(cls, val):
        if len(val) <= cls.Index.SUBTYPE:
            return cls._unknown_validator(val)
        type_ = cls.Type(val[cls.Index.TYPE])
        if type_ is cls.Type.UNKNOWN:
            return cls._unknown_validator(val)
        subtype_cls = type_.subtype_class
        subtype = subtype_cls(val[cls.Index.SUBTYPE])
        if subtype is subtype_cls.UNKNOWN:
            return cls._unknown_validator(val, type_, subtype)
        argnum = subtype.argnum
        msg_index = cls.Index.ARGS_OR_MSG
        args = None
        msg = None
        if argnum > 0:
            msg_index += 1
            args = val[cls.Index.ARGS_OR_MSG]
        if len(val) > msg_index:
            msg = val[msg_index]
        args, valid_args = cls._parse_args(args, type_, subtype, argnum)
        if not valid_args:
            warn(InvalidArguments(type_, subtype, args))
        return cls(type_, subtype, args, not valid_args, msg)

    def __init__(self, type_, subtype, args, bad_args, error_msg):
        self.type = type_
        self.subtype: Subtype = subtype
        self.args = args
        self.error_msg = error_msg
        self.bad_args = bad_args

    def validate(self, elem, value: str):
        if self.has_unknown_type() or self.bad_args:
            return
        is_ok = False
        if self.type is self.Type.NUMBER:
            is_ok = self._validate_number(value)
        if self.type is self.Type.TEXT:
            is_ok = self._validate_text(value)
        if self.type is self.Type.LENGTH:
            is_ok = self._validate_length(value)
        if self.type is self.Type.REGEX:
            is_ok = self._validate_regex(value)
        if not is_ok:
            raise InvalidText(elem, value, details=self._descr())

    def to_str(self):
        if self.has_unknown_type():
            return '! Unknown validator !'
        return f'! {self._descr()} !'

    def has_unknown_type(self):
        return self.type is self.Type.UNKNOWN or self.subtype is self.type.subtype_class.UNKNOWN

    @classmethod
    def _unknown_validator(cls, val, type_=None, subtype=None):
        warn(UnknownValidator(cls, val))
        return cls(type_ or cls.Type.UNKNOWN, subtype or cls.Type.UNKNOWN,
                   args=None, bad_args=False, error_msg=None)

    @classmethod
    def _parse_args(cls, args, type_, subtype, argnum):
        """
        Convert arguments to needed type. All args are received as strings
        Return value: converted args and a value indicating if conversion was successful
        """
        if args is None:
            return None, not argnum  # Error if args are required, but not found
        if len(args) != argnum:
            return args, False
        if type_ is cls.Type.TEXT:
            return args, True  # needs a string
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
        s = self.subtype.descr(self.args)
        if self.type is self.Type.LENGTH:
            return s
        return 'Allowed values: ' + s

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
        if self.subtype is NumberTypes.lE:
            return val <= arg
        if self.subtype is NumberTypes.EQ:
            # if arg == 2.0, "1.99..9" will pass validation.
            # It's ok, as long as the value is accepted by server
            return val == arg
        if self.subtype is NumberTypes.NE:
            return val != arg
        if self.subtype is NumberTypes.RANGE:
            # THe first arg can be greater than the second
            # In this case all values will be invalid. Raise another error? (see MisconfiguredGrid)
            return self.args[0] <= val <= self.args[1]
        if self.subtype is NumberTypes.NOT_RANGE:
            return not self.args[0] <= val <= self.args[1]

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

    def _validate_length(self, val):
        if self.subtype is LengthTypes.MIN_LENGTH:
            return len(val) >= self.args[0]
        if self.subtype is LengthTypes.MAX_LENGTH:
            return len(val) <= self.args[0]

    def _validate_regex(self, val):
        if self.subtype is RegexTypes.CONTAINS:
            return self.args[0].search(val) is not None
        if self.subtype is RegexTypes.NOT_CONTAINS:
            return self.args[0].search(val) is None
        if self.subtype is RegexTypes.MATCHES:
            return self.args[0].match(val) is not None
        if self.subtype is RegexTypes.NOT_MATCHES:
            return self.args[0].match(val) is None


class GridValidator:
    class Type(Enum):
        EXCLUSIVE_COLUMNS = auto()
        UNKNOWN = auto()

    @classmethod
    def parse(cls, val):
        if val == [[8, 205]]:
            return cls(type_=cls.Type.EXCLUSIVE_COLUMNS)
        warn(UnknownValidator(cls, val))
        return cls(type_=cls.Type.UNKNOWN)

    def __init__(self, *, type_):
        self.type = type_

    def validate(self, elem, values: List[List[str]]):
        if self.type == self.Type.UNKNOWN:
            return
        if elem.is_misconfigured():
            raise MisconfiguredGrid(elem, values)
        cnt = Counter()
        for row in values:
            if row:
                cnt.update(row)
                col, count = max(cnt.items(), key=lambda x: x[1])
                if count > 1:
                    raise SameColumn(elem, values, col)

    def to_str(self):
        if self.type == self.Type.EXCLUSIVE_COLUMNS:
            return '! Max 1 response per column !'
        return '! Unknown validator !'
