"""
Tests in this module assert that raw form data format is unchanged
and forms can be correctly parsed.
"""


import json
from typing import Iterable

import pytest

from gforms import Form

from . import util
from . import form_dumps
from .util import skip_requests_exceptions
from .conftest import require_urls


pytestmark = require_urls


def parametrize_form_types(form_types: Iterable):
    return pytest.mark.parametrize(
        'form_with_dump, form_type',
        zip(form_types, form_types),
        indirect=['form_with_dump'],
        ids=list(form_types)
    )


@pytest.fixture(scope='module')
@skip_requests_exceptions
def form_with_dump(session, request):
    from . import urls

    form_type = request.param
    url = getattr(urls.FormUrl, form_type)
    return util.form_with_dump(url, session)


@parametrize_form_types(form_dumps.FormData.Elements)
def test_elements_dump(form_with_dump, form_type):

    def extract_elements(data):
        return data[Form._DocIndex.FORM][Form._FormIndex.ELEMENTS]

    form, dump = form_with_dump
    # changed format of settings or other form attributes should not affect these tests
    assert extract_elements(dump) == extract_elements(getattr(form_dumps.FormData, form_type))


@parametrize_form_types(form_dumps.FormData.Settings)
def test_settings_dump(form_with_dump, form_type):
    form, dump = form_with_dump
    assert dump == getattr(form_dumps.FormData, form_type)


@pytest.mark.parametrize('form_with_dump', ['edit'], indirect=True)
def test_edit_draft(form_with_dump):
    form, _ = form_with_dump
    assert json.loads(form._draft)[0] == json.loads(form_dumps.Draft.response1)[0]
