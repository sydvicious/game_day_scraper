#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


import os
from setuptools import setup

try:
    here = os.path.dirname(os.path.abspath(__file__))
    description = file(os.path.join(here, 'README.md')).read()
except (OSError, IOError):
    description = None

version = '0.1'

deps = ['requests == 1.2.2',
      ]

setup(name='game_day_scraper',
      version=version,
      description='Script to download game records from MLB's GameDay server.',
      long_description=description,
      # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      classifiers=[],
      keywords='mlb',
      author='Syd Polk',
      author_email='sydpolk@gmail.com',
      url='http://github.com/sydvicious/game_day_scraper',
      license='Mozilla Public License 2.0 (MPL 2.0)',
      packages=['game_day_scraper'],
      zip_safe=False,
      install_requires=deps,
      )
