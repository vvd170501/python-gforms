#!/usr/bin/env python3

import argparse
import sys
import os

# Workaround for relative imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(BASE_DIR))

from tests.form_dumps import FormData
from tests.util import form_with_dump
try:
    from tests.urls import FormUrl
except ImportError:
    print('Form urls are not available', file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('category')
    args = parser.parse_args()

    category = getattr(FormData, args.category)
    for name in category:
        url = getattr(FormUrl, name)
        _, dump = form_with_dump(url)
        print(f'{name} = {dump}')

if __name__ == '__main__':
    main()
