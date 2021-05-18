import pytest

from gforms.validators import TextValidator, NumberTypes, TextTypes, LengthTypes, RegexTypes


class TestTextValidators:
    @pytest.fixture
    def kwargs(self):
        return {
            'type_': TextValidator.Type.UNKNOWN,
            'subtype': TextValidator.Type.UNKNOWN,
            'args': None,
            'bad_args': False,
            'error_msg': None
        }

    @pytest.fixture
    def type_number(self, kwargs):
        kwargs['type_'] = TextValidator.Type.NUMBER

    @pytest.fixture
    def type_text(self, kwargs):
        kwargs['type_'] = TextValidator.Type.TEXT

    @pytest.fixture
    def type_length(self, kwargs):
        kwargs['type_'] = TextValidator.Type.LENGTH

    @pytest.fixture
    def type_regex(self, kwargs):
        kwargs['type_'] = TextValidator.Type.REGEX

    @pytest.fixture
    def validator(self, kwargs):
        return TextValidator(**kwargs)

    # TODO add tests?
