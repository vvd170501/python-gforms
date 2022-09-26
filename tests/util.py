from functools import wraps

import pytest
import requests

from gforms import Form


def skip_requests_exceptions(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.exceptions.RequestException as e:
            pytest.skip(f'Requests error: {e}')

    return wrapper


def rewrite_links(data):
    from . import fake_urls
    from . import urls

    if isinstance(data, list):
        return [rewrite_links(elem) for elem in data]
    if isinstance(data, dict):
        return {rewrite_links(key): rewrite_links(value) for key, value in data.items()}
    if isinstance(data, str):
        data = data.replace(urls._yt_link, fake_urls._yt_link)
        if len(data) == 48:  # image id
            return '0' * len(data)
        return data
    return data


def form_with_dump(url, session=None):
    form_data = []

    form = Form()
    orig_parse = form._parse

    def dump(data):
        # replace video url and image ids
        data = rewrite_links(data)
        # erase the form url
        data[Form._DocIndex.URL] = '0' * len(data[Form._DocIndex.URL])
        nonlocal form_data
        form_data = data
        return orig_parse(data)

    form._parse = dump
    form.load(url, session=session)

    return form, form_data
