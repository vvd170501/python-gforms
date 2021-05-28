import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Tuple

import pytest
import requests

from gforms import Form

from .util import skip_requests_exceptions


# -------------------- Skippable tests --------------------


class Skippable:
    """Xfail all remaining tests if a test marked with "required" fails"""
    pass


# store history of failures per test class name and index in parametrize (if parametrize was used)
_failed_required_tests: Dict[str, Dict[Tuple[int, ...], str]] = {}


def pytest_configure(config):
    config.addinivalue_line(
        'markers',
        'required: use with tests in Skippable classes to xfail all remaining tests on failure'
    )


# See https://docs.pytest.org/en/6.2.x/example/simple.html#incremental-testing-test-steps
def pytest_runtest_makereport(item, call):
    if 'required' in item.keywords:
        if call.excinfo is not None:  # the test has failed
            cls_name = str(item.cls)
            # retrieve the index of the test (if parametrize is used)
            parametrize_index = (
                tuple(item.callspec.indices.values())
                if hasattr(item, 'callspec')
                else ()
            )
            # retrieve the name of the test function
            test_name = item.originalname or item.name
            # store in _test_failed_incremental the original name of the failed test
            _failed_required_tests.setdefault(cls_name, {}).setdefault(
                parametrize_index, test_name
            )


def pytest_runtest_setup(item):
    if issubclass(item.cls, Skippable):
        cls_name = str(item.cls)
        # check if a previous test has failed for this class
        if cls_name in _failed_required_tests:
            # retrieve the index of the test (if parametrize is used)
            parametrize_index = (
                tuple(item.callspec.indices.values())
                if hasattr(item, "callspec")
                else ()
            )
            # retrieve the name of the first test function to fail for this class name and index
            test_name = _failed_required_tests[cls_name].get(parametrize_index, None)
            # if name found, test has failed for the combination of class name & test name
            if test_name is not None:
                pytest.xfail("previous test failed ({})".format(test_name))


# -------------------- Dynamic test generation --------------------


def pytest_generate_tests(metafunc):
    def parametrize_invalid_types(what=''):
        """Parametrizes fixture(s) for testing invalid arg types.

        The test being parametrized must use the "invalid_type"
        or "invalid_something_type" fixture.

        If the test class has an allow_lists (allow_stings) attribute,
        then the corresponding type is not used.
        The same applies to "allow_something_(lists|strings)" attributes.
        """
        values = [None]  # possible "if (not) value" / "if value is None" checks
        if 'Scale' not in metafunc.cls.__name__:
            values.append(True)  # True is also an int, so it is a valid value for Scale

        if not getattr(metafunc.cls, f'allow_{what}strings'):
            values.append('')  # disallow strings (lists) for elements which should not accept them
        if not getattr(metafunc.cls, f'allow_{what}lists'):
            values.append([])
        metafunc.parametrize(f'invalid_{what}type', values, ids=lambda val: repr(val))

    def parametrize_choice_types(uses_choice_getter, uses_choice_val_getter):
        """Parametrizes fixture(s) for testing ChoiceValue.

        Parametrize the "get_choice" fixture.
        The parametrized fixture is a function:
        get_choice(opt: Option) -> opt | opt.value

        If the "get_choice_value" fixture is requested,
        parametrize it with matching values.THe result is a function,
        such that get_choice_value(get_choice(opt)) is always a string.
        """
        fixtures = []
        if uses_choice_getter:
            fixtures.append('get_choice')
        if uses_choice_val_getter:
            fixtures.append('get_choice_value')
        values = [(True, True), (False, False)] if uses_choice_getter and uses_choice_val_getter \
            else [True, False]
        metafunc.parametrize(
            ', '.join(fixtures),
            values,
            indirect=fixtures,
            ids=['str', 'Option']
        )

    def parametrize_validator_data():
        """See comments in ValidatedTest."""
        if 'misconfigured' in metafunc.function.__name__:
            args = metafunc.cls.misconfigured
        else:
            args = metafunc.cls.validators
        # Is it possible to entirely remove (not skip) a test if args is empty?

        # test id ==  f'{val_type}.{val_subtype}'
        ids = [f'{arg[0][0].name}.{arg[0][1].name}' for arg in args]
        metafunc.parametrize(
            'validator_data',
            args,
            indirect=['validator_data'],
            ids=ids,
        )

    for fixturename in metafunc.fixturenames:
        match = re.match(r'invalid_(\w+_)?type', fixturename)
        if match:
            parametrize_invalid_types(match.group(1) or '')

    uses_choice_getter = 'get_choice' in metafunc.fixturenames
    uses_choice_val_getter = 'get_choice_value' in metafunc.fixturenames
    if uses_choice_getter or uses_choice_val_getter:
        parametrize_choice_types(uses_choice_getter, uses_choice_val_getter)
    if 'validator_data' in metafunc.fixturenames:
        parametrize_validator_data()


# -------------------- URLs and form loading --------------------


url_module = Path(__file__).parent / 'urls.py'
with open(url_module, 'rb') as f:
    urls_available = f.read(10) != b'\x00GITCRYPT\x00'


def load_dump(form_type):
    from . import form_dumps
    form = Form('https://docs.google.com/forms/d/e/0123456789abcdef/viewform')
    form._fbzx = '123456789'
    form._draft = f'[null,null,"{form._fbzx}"]\n'
    form._history = '0'
    data = getattr(form_dumps, form_type)
    form._parse(data)
    form._is_loaded = True
    return form


@pytest.fixture(scope='session')
def url():
    if urls_available:
        from . import urls
        return urls
    else:
        from . import form_dumps
        class FakeUrlModule:
            yt_url = form_dumps.yt_url
        return FakeUrlModule


USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ' \
             'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'


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


class BaseFormTest(Skippable, ABC):
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

    def test_to_str(self, form):
        # NOTE These tests only assert that to_str doesn't fail. The return value is not checked
        _ = form.to_str()
