import random
import re
from enum import Enum
from typing import Optional

SEP_WIDTH = 60  # implement dynamic width?
RADIO_SYMBOLS = ('◯', '⦿')
CHECKBOX_SYMBOLS = ('☐', '☒')


# Pattern from form submision page
EMAIL_REGEX = re.compile(
    r"^[+a-zA-Z0-9_.!#$%&'*\/=?^`{|}~-]+@([a-zA-Z0-9-]+\.)+[a-zA-Z0-9]{2,63}$"
)

# From https://gist.github.com/dperini/729294
URL_REGEX = re.compile(
    r'^(?:(?:(?:https?|ftp):)?\/\/)(?:\S+(?::\S*)?@)?(?:(?!(?:10|127)(?:\.\d{1,3}){3})'
    r'(?!(?:169\.254|192\.168)(?:\.\d{1,3}){2})(?!172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})'
    r'(?:[1-9]\d?|1\d\d|2[01]\d|22[0-3])(?:\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])){2}'
    r'(?:\.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-4]))|(?:(?:[a-z0-9\u00a1-\uffff]'
    r'[a-z0-9\u00a1-\uffff_-]{0,62})?[a-z0-9\u00a1-\uffff]\.)+'
    r'(?:[a-z\u00a1-\uffff]{2,}\.?))(?::\d{2,5})?(?:[/?#]\S*)?$'
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


def list_get(lst, index, default=None):
    if len(lst) > index:
        return lst[index]
    return default


def page_separator(indent):
    return '=' * SEP_WIDTH


def elem_separator(indent):
    return '—' * (SEP_WIDTH - indent)


def add_indent(text, indent):
    if not indent:
        return text
    spaces = ' ' * indent
    return ''.join(spaces + line for line in text.splitlines(keepends=True))


def random_subset(a, *, prob=0.5, min_size: Optional[int] = None, max_size: Optional[int] = None):
    """Choose a random subset of a.

    Args:
        a: the input sequence
        prob: Probability to pick an element
            (when called without size constraints).
        min_size: Minimal size of the result.
        max_size: Maximal size of the result.
    Returns:
        A random subset of a
    """
    def subset(a, prob):
        res = []
        remaining = []
        for el in a:
            if random.random() < prob:
                res.append(el)
            else:
                remaining.append(el)
        return res

    if min_size is None:
        min_size = 0
    if max_size is None:
        max_size = len(a)
    min_size = max(min_size, 0)
    max_size = min(max_size, len(a))

    if min_size > max_size:
        raise ValueError(f'Invalid size range for random_subset: [{min_size}, {max_size}]')

    tmp = random.sample(a, max_size)
    return tmp[:min_size] + subset(tmp[min_size:], prob)  # tweak distribution?
