from collections import Counter
from enum import Enum, auto
from typing import List
from warnings import warn


from .errors import MisconfiguredGrid, SameColumn, UnknownValidator


class TextValidator:  # TODO
    class Type(Enum):
        pass

    def __init__(self):
        pass

    def validate(self, value: str):
        pass


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
