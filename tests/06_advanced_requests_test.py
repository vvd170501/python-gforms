from bs4 import BeautifulSoup

from gforms import Form

from .conftest import RealFormTest, require_urls


pytestmark = require_urls


class TestBackHack(RealFormTest):
    form_type = 'back_hack'

    # Form:
    # - Page 1: required UserEmail and required Radio
    #   (to check if "back" works without filling these elements)
    # - Page 2: empty
    #   (just added this for more variety. Who knows, maybe an empty page might break something?)
    # - Page 3: required Radio, go to submit
    #   (same as P1, but for the last reachable page, just before the final submission)
    # - Page 4 (unreachable): Comment "Ok, you won"
    # - Page 5: empty (to ensure that the SUBMIT page is not reachable from P4)

    def test_fetch_page(self, form, session):
        resp = form._fetch_page(session, form.pages[3])
        soup = BeautifulSoup(resp.text, 'html.parser')
        assert soup.find(string='Ok, you won') is not None


class TestResolveImages:
    """See form description in 10_parse_form_test.py::TestImages."""

    def test_resolve_images(self, session, capsys):
        from . import urls
        form = Form()
        form.load(urls.FormUrl.images, session, resolve_images=True)
        captured = capsys.readouterr()
        assert captured.err == ''
