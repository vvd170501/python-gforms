import re

import pytest

from gforms.errors import ClosedForm, InvalidURL, NoSuchForm, EditingDisabled

from .conftest import FormTest, urls_available


class TestLoadErrors:
    def test_invalid_url(self, load_form):
        url = 'https://example.com'
        with pytest.raises(InvalidURL, match=re.escape(url)):
            load_form(url)

    def test_404(self, load_form):
        url = 'https://docs.google.com/forms/d/e/fake_form_id/viewform'
        with pytest.raises(NoSuchForm, match=re.escape(url)):
            load_form(url)

    def test_closed(self, load_form):
        with pytest.raises(ClosedForm, match='00_Closed'):
            load_form('https://docs.google.com/forms/d/e/1FAIpQLSeq_yONm2qxkvvuY5BI9E3-rDD7RxIQHo9-R_-hy1mZlborKA/viewform')

    def test_editing_disabled(self, load_form):
        if not urls_available:
            pytest.skip('Urls are not available')
        from . import urls
        url = urls.FormUrl.editing_disabled
        with pytest.raises(EditingDisabled, match=re.escape(url)):
            load_form(url)


# check that real urls are accepted
class TestLoadOk(FormTest):
    form_type = 'empty'

    def test_load(self, form):
        pass


# check that short (real) urls are accepted
class TestShortLoadOk(FormTest):
    form_type = 'empty_short'

    def test_load(self, form):
        pass


# !! test signin (file upload)
