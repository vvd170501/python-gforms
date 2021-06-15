"""
Tests in this module assert that raw form data format is unchanged
and forms can be correctly parsed.
"""


import json

import pytest
import requests.models

from gforms import Form
from tests import form_dumps
from tests.util import skip_requests_exceptions
from .conftest import urls_available

from . import util


pytestmark = pytest.mark.skipif(not urls_available, reason='Urls are not available')


def parametrize_form_types(form_types):
    return pytest.mark.parametrize(
        'form_with_dump, form_type',
        zip(form_types, form_types),
        indirect=['form_with_dump'],
        ids=form_types
    )


@pytest.fixture(scope='module')
@skip_requests_exceptions
def form_with_dump(session, request):
    from . import urls

    form_type = request.param
    url = getattr(urls.FormUrl, form_type)
    return util.form_with_dump(url, session)


element_test_forms = [name for name in form_dumps.FormData.Elements.__dict__ if not name.startswith('_')]
settings_test_forms = [name for name in form_dumps.FormData.Settings.__dict__ if not name.startswith('_')]


@parametrize_form_types(element_test_forms)
def test_elements_dump(form_with_dump, form_type):

    def extract_elements(data):
        return data[Form._DocIndex.FORM][Form._FormIndex.ELEMENTS]

    form, dump = form_with_dump
    # changed format of settings or other form attributes should not affect these tests
    assert extract_elements(dump) == extract_elements(getattr(form_dumps.FormData, form_type))


@parametrize_form_types(settings_test_forms)
def test_settings_dump(form_with_dump, form_type):
    form, dump = form_with_dump
    assert dump == getattr(form_dumps.FormData, form_type)


@pytest.mark.parametrize('form_with_dump', ['edit'], indirect=True)
def test_edit_draft(form_with_dump):
    form, _ = form_with_dump
    assert json.loads(form._draft)[0] == json.loads(form_dumps.Draft.response1)[0]
