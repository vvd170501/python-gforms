import re

import pytest

from gforms.errors import ClosedForm, InvalidURL, NoSuchForm, EditingDisabled, SigninRequired

from .conftest import RealFormTest, require_urls


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

    @require_urls
    def test_editing_disabled(self, load_form):
        from . import urls  # use a fixture?
        url = urls.FormUrl.editing_disabled
        with pytest.raises(EditingDisabled, match=re.escape(url)):
            load_form(url)

    @require_urls
    def test_signin_required(self, load_form):
        from . import urls
        url = urls.FormUrl.file_upload
        with pytest.raises(SigninRequired):
            load_form(url)


# check that real urls are accepted
class TestLoadOk(RealFormTest):
    form_type = 'empty'

    def test_load(self, form):
        pass


# check that short (real) urls are accepted
class TestShortLoadOk(RealFormTest):
    form_type = 'empty_short'

    def test_load(self, form):
        pass
