from setuptools import setup, find_packages
from gforms import __version__


with open('README.md', 'r', encoding='utf-8') as f:
    readme = f.read()


setup(
    name='gforms',
    description='Google Forms wrapper for Python',
    long_description=readme,
    long_description_content_type='text/markdown',
    url='https://github.com/vvd170501/python-gforms',
    version=__version__,
    packages=find_packages(),
    install_requires=[
        'requests',
        'beautifulsoup4',
    ],
    extras_require={
        'dev': [
            'pytest',
        ]
    }

)
