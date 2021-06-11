from functools import wraps

import pytest
import requests

from gforms import Form


class StaticSession(requests.Session):
    """A session which caches responses for GET requests."""

    def __init__(self):
        super().__init__()
        self._cache = {}

    def get(self, url, **kwargs):
        key = (url, *kwargs.items())
        if key in self._cache:
            return self._cache[key]
        resp = super(StaticSession, self).get(url, **kwargs)
        self._cache[key] = resp
        return resp


def skip_requests_exceptions(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.exceptions.RequestException as e:
            pytest.skip(f'Requests error: {e}')

    return wrapper


def dump(url):
    """Dumps raw form data (for saving to form_dumps.py)"""
    form_data = []

    def _dump(data):
        nonlocal form_data
        form_data = data

    form = Form()
    form._parse = _dump
    form.load(url)

    form_data[Form._DocIndex.URL] = '0' * len(form_data[Form._DocIndex.URL])
    return form_data
