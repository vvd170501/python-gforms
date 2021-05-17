import random
import re
from enum import Enum

SEP_WIDTH = 50
RADIO_SYMBOLS = ('◯', '⦿')
CHECKBOX_SYMBOLS = ('☐', '☒')


# Pattern from form submision page
EMAIL_REGEX = re.compile(
    r"^[+a-zA-Z0-9_.!#$%&'*\/=?^`{|}~-]+@([a-zA-Z0-9-]+\.)+[a-zA-Z0-9]{2,63}$"
)

# From https://gist.github.com/dperini/729294
URL_REGEX = re.compile(
    r'^(?:(?:(?:https?|ftp):)?\/\/)(?:\S+(?::\S*)?@)?(?:(?!(?:10|127)(?:\.\d{1,3}){3})(?!('
    r'?:169\.254|192\.168)(?:\.\d{1,3}){2})(?!172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})(?:['
    r'1-9]\d?|1\d\d|2[01]\d|22[0-3])(?:\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])){2}(?:\.(?:['
    r'1-9]\d?|1\d\d|2[0-4]\d|25[0-4]))|(?:(?:[a-z0-9\u00a1-\uffff][a-z0-9\u00a1-\uffff_-]{0,'
    r'62})?[a-z0-9\u00a1-\uffff]\.)+(?:[a-z\u00a1-\uffff]{2,}\.?))(?::\d{2,5})?(?:[/?#]\S*)?$ '
)


class DefaultEnum(Enum):
    @classmethod
    def _missing_(cls, value):
        return cls.__members__['UNKNOWN']  # is it possible to add a member when creating a class?


class ArgEnum(Enum):
    def __new__(cls, value, arg):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.arg = arg
        return obj


def page_separator(indent):
    return '=' * SEP_WIDTH


def elem_separator(indent):
    return '—' * (SEP_WIDTH - indent)


def add_indent(text, indent):
    if not indent:
        return text
    spaces = ' ' * indent
    return ''.join(spaces + line for line in text.splitlines(keepends=True))


def random_subset(a, nonempty=True):
    def subset(a):
        res = []
        for el in a:
            if random.random() < 0.5:
                res.append(el)
        return res

    if nonempty:
        if not a:
            raise ValueError('Cannot generate a non-empty subset of an empty set')
        if len(a) == 1:
            return a[:]

    res = subset(a)
    if nonempty:
        while not res:  # P(>2 iters) <= 1/16
            res = subset(a)
    return res
