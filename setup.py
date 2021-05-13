from setuptools import setup, find_packages
from gforms import __version__


setup(
    name='gforms',
    description='Google Forms wrapper',
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
