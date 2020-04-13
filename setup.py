#!/usr/bin/env python

from ebssnapshot import metadata
from setuptools import setup

setup(name=metadata.__project__,
      version=metadata.__version__,
      description=metadata.__description__,
      author=metadata.__author__,
      author_email=metadata.__email__,
      url=metadata.__url__,
      scripts=["scripts/ebssnap"],
      packages=['ebssnapshot'],
      install_requires=open("requirements.txt").read().splitlines(),
      )
