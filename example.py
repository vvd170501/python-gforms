#!/usr/bin/env python3

import argparse
import random
import string
import sys
from math import ceil
from time import sleep, asctime, time as time_now
from datetime import date, datetime, time, timedelta

import requests
try:
    from fake_useragent import FakeUserAgent
except ImportError:
    print('This program needs fake-useragent to run')
    sys.exit(1)

from gforms import Form
from gforms.errors import InfiniteLoop, ClosedForm, ValidationError
from gforms.elements_base import Grid
from gforms.elements import UserEmail
from gforms.elements import Dropdown, Scale, Radio, Checkboxes, Value
from gforms.elements import Date, DateTime, Time, Duration


def lowexp(n=10, m=None):
    """Returns mostly low integer values in range [1, n].

    May be useful for Scale elements

    n: The maximal value.
    m: The mean of used exponential distribution.
    """
    if m is None:
        # You may want to modify m to get higher / lower values.
        # ~2.5% chance of 7+ if n == 10
        # ~2.5% chance of 4+ if n == 5
        m = 6 / n
    while True:
        res = ceil(random.expovariate(m))
        if res <= n:
            return res


def highexp(n=10, m=None):
    """Returns mostly high integer values in range [1, n].

    For details see lowexp.
    """
    return n + 1 - lowexp(n, m)


def random_email():
    domain = random.choice(['example.com', 'example.org', 'example.net'])
    username = ''.join(random.choices(string.ascii_lowercase, k=random.randint(6, 8)))
    return f'{username}@{domain}'


class Filler:
    def __init__(self):
        self.mapping = {}

    def callback(self, elem, i, j):
        if isinstance(elem, UserEmail):
            return random_email()
        if isinstance(elem, Scale):
            return lowexp(len(elem.options))  # custom choice function
        if isinstance(elem, Radio):
            return Value.DEFAULT  # random choice
        if isinstance(elem, Dropdown):
            return Value.DEFAULT  # random choice

        # NOTE The default callback may fail on elements with validators (Grid, Checkboxes).
        if isinstance(elem, Grid):
            return Value.DEFAULT  # random choices
        if isinstance(elem, Checkboxes):
            return Value.DEFAULT  # random choices

        # Generate random date / time values
        if isinstance(elem, Date) or isinstance(elem, DateTime):
            today = date.today().toordinal()
            first = today - 10
            last = today + 10
            date_part = date.fromordinal(random.randint(first, last))
            if isinstance(elem, Date):
                return date_part
            minutes = random.randint(0, 24 * 60 - 1)
            time_part = time(minutes // 60, minutes % 60)
            return datetime.combine(date_part, time_part)
        if isinstance(elem, Time):
            minutes = random.randint(0, 24 * 60 - 1)
            return time(minutes // 60, minutes % 60)
        if isinstance(elem, Duration):
            return timedelta(seconds=random.randint(0, 24*3600))

        # Text inputs
        if elem.id not in self.mapping:
            print('Cannot determine a default value for the element:')
            print(elem.to_str(2))
            self.mapping[elem.id] = input(
                'Comma-separated choice list for the element (e.g. "test,qwe,rty"): '
            ).split(',')
        return random.choice(self.mapping[elem.id])


def main():
    ua = FakeUserAgent()
    # A session for form loading and submission
    sess = requests.session()
    sess.headers['User-Agent'] = ua.chrome

    # Mean time between submissions
    mean_dt = 60

    parser = argparse.ArgumentParser()
    parser.add_argument(
        'url',
        help='The form url (https://docs.google.com/forms/d/e/.../viewform)'
    )
    args = parser.parse_args()

    form = Form()
    form.load(args.url, session=sess)
    filler = Filler()

    # Show the form
    print(form.to_str(2))

    # Use filler to cache custom callback values, if needed (will be reused later)
    form.fill(filler.callback, fill_optional=True)

    # Show the form with answers
    print(form.to_str(2, include_answer=True))
    print()

    for i in range(10):
        last = time_now()
        print(f'[{asctime()}] Submit {i+1}... ', end='')
        sep = ''
        filled = False
        for _ in range(10):
            # Retry if InfiniteLoop is raised
            try:
                form.fill(filler.callback, fill_optional=True)
                filled = True
                break
            except InfiniteLoop:
                sep = ' '
                print('X', end='')
                sleep(0.1)
            except ValidationError as err:
                # Most probably the default callback failed on an element with a validator.
                print(f'{sep}Failed: {err}')
                sleep(1)
                break

        if not filled:
            continue

        try:
            form.submit(session=sess)
            # You may want to use history emulation:
            #   submission is faster, but it is still experimental
            # form.submit(session=sess, emulate_history=True)
            print(sep + 'OK', end='')
        except ClosedForm:
            print(sep + 'Form is closed')
            break
        except RuntimeError:
            # Incorrect response code or page prediction failed
            print(sep + 'Failed', end='')

        # Poisson distribution for (submissions / timeframe)
        delta = random.expovariate(1 / mean_dt)
        print(f', sleeping for {round(delta)}s')
        sleep(max(0.0, last + delta - time_now()))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('WTF', e)
