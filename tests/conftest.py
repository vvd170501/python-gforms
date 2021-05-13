import pytest
import requests

from gforms import Form

from .util import skip_requests_exceptions


USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'


@pytest.fixture(scope='package')
def session():
    sess = requests.session()
    sess.headers['User-Agent'] = USER_AGENT
    return sess



@pytest.fixture
def load_form(request, session):
    @skip_requests_exceptions
    def load_form(url):
        form = Form(url)
        form.load(session)
        return form

    return load_form


@pytest.fixture(scope='session')
def url():
    try:
        from . import urls
        return urls
    except Exception:
        pytest.skip('URLs are encrypted')
