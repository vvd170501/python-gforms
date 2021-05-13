from functools import wraps

import pytest
import requests


def skip_requests_exceptions(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.exceptions.RequestException as e:
            pytest.skip(f'Requests error: {e}')

    return wrapper
