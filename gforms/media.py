from enum import Enum

from gforms.util import list_get


class Alignment(Enum):
    LEFT = 0
    CENTER = 1
    RIGHT = 2


class ImageObject:
    """A base class for image elements and attachments.

    Attributes:
        width: Self-explanatory.
        height: Self-explanatory.
        alignment: Optional image alignment.
        id: Some kind of ID (cosmoId?).
        url: Image URL, optional.
            Present only if the form was loaded with resolve_images=True.
    """

    class _Index:
        ID = 0
        STYLE = 2

    @classmethod
    def parse(cls, image_data):
        return cls(**cls._parse(image_data))

    @classmethod
    def _parse(cls, image_data):
        return {
            'id_': image_data[cls._Index.ID],
            **parse_style(image_data[cls._Index.STYLE]),
        }

    def __init__(self, *, width, height, alignment, id_, url=None, **kwargs):
        super().__init__(**kwargs)
        self.width = width
        self.height = height
        self.alignment = alignment
        self.id = id_
        self.url = url

    def to_str(self, indent=0):
        descr = f'Image'
        details = f': {self.url}' if self.url else ''
        return f'<{descr}{details}>'


class _StyleIndex:
    WIDTH = 0
    HEIGHT = 1
    ALIGNMENT = 2


def parse_style(data):
    alignment_val = list_get(data, _StyleIndex.ALIGNMENT)
    return {
        'width': data[_StyleIndex.WIDTH],
        'height': data[_StyleIndex.HEIGHT],
        'alignment': Alignment(alignment_val) if alignment_val is not None else None,
    }
