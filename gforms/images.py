from enum import Enum

from gforms.util import list_get


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

    class Alignment(Enum):
        LEFT = 0
        CENTER = 1
        RIGHT = 2

    class _Index:
        ID = 0
        IMAGE_ATTRS = 2
        WIDTH = 0
        HEIGHT = 1
        ALIGNMENT = 2

    @classmethod
    def parse(cls, image_data):
        return cls(**cls._parse(image_data))

    @classmethod
    def _parse(cls, image_data):
        img_attrs = image_data[cls._Index.IMAGE_ATTRS]
        return {
            'id_': image_data[cls._Index.ID],
            'width': img_attrs[cls._Index.WIDTH],
            'height': img_attrs[cls._Index.HEIGHT],
            'alignment': cls.Alignment(list_get(img_attrs, cls._Index.ALIGNMENT)),
        }

    def __init__(self, *, width, height, alignment, id_, url=None, **kwargs):
        super().__init__(**kwargs)
        self.width = width
        self.height = height
        self.alignment = alignment
        self.id = id_
        self.url = url

    def size_str(self):
        return f'{self.width}x{self.height}'

    def to_str(self, indent=0):
        descr = f'Image ({self.size_str()})'
        details = f': {self.url}' if self.url else ''
        return f'<{descr}{details}>'
