from abc import ABC, abstractmethod
from pathlib import Path

import pytest
import requests

from gforms import Form

from .util import skip_requests_exceptions


url_module = Path(__file__).parent / 'urls.py'
with open(url_module, 'rb') as f:
    urls_available = f.read(10) != b'\x00GITCRYPT\x00'


USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'


def load_dump(form_type):
    from . import form_dumps
    form = Form('https://docs.google.com/forms/d/e/0123456789abcdef/viewform')
    form._fbzx = '123456789'
    form._draft = f'[null,null,"{form._fbzx}"]\n'
    form._history = '0'
    data = getattr(form_dumps, form_type)
    form._parse(data)
    return form


def pytest_generate_tests(metafunc):
    if 'invalid_type' in metafunc.fixturenames:
        values = [{}, None, False, True]
        if not metafunc.cls.allow_strings:
            values.append('')
        if not metafunc.cls.allow_lists:
            values.append([])
        metafunc.parametrize('invalid_type', values, ids=lambda val: str(val) or '""')


@pytest.fixture(scope='session')
def url():
    if urls_available:
        from . import urls
        return urls
    else:
        class FakeUrlModule:
            yt_url = 'https://youtu.be/dQw4w9WgXcQ'
        return FakeUrlModule


@pytest.fixture(scope='package')
def session():
    sess = requests.session()
    sess.headers['User-Agent'] = USER_AGENT
    return sess


@pytest.fixture(scope='package')
def load_form(session):

    @skip_requests_exceptions
    def load_form(url):
        form = Form(url)
        form.load(session)
        return form

    return load_form


class BaseFormTest(ABC):
    @property
    @abstractmethod
    def form_type(self) -> str:
        raise NotImplementedError()

    @pytest.fixture(scope='class')
    def form(self, load_form, url):
        if urls_available:
            link = getattr(url, self.form_type)
            return load_form(link)
        else:
            return load_dump(self.form_type)
