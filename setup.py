import re
from setuptools import setup, find_packages


with open('README.md', 'r', encoding='utf-8') as f:
    readme = f.read()


with open('gforms/__init__.py', encoding='utf-8') as f:
    version = re.search(r"__version__ = '(.+)'", f.read()).group(1)


setup(
    name='gforms',
    description='Google Forms wrapper for Python',
    long_description=readme,
    long_description_content_type='text/markdown',
    url='https://github.com/vvd170501/python-gforms',
    version=version,
    packages=find_packages(),
    install_requires=[
        'beautifulsoup4',
        'requests',
    ],
    extras_require={
        'dev': [
            'pytest',
        ]
    },
)
