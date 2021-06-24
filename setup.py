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
    author='vvd170501',
    url='https://github.com/vvd170501/python-gforms',

    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],

    packages=['gforms'],
    version=version,
    license_files=('LICENSE',),

    python_requires='>=3.6',
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
