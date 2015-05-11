#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime, timedelta
from optparse import OptionParser, OptionGroup
import os
import pkg_resources
import re
import requests
import sys
import time
import urllib
import logging
from urlparse import urlparse

from parser import DirectoryParser
from urlparse import urljoin

import progressbar as pb

# Base URL for the path to all game files
BASE_URL = 'http://gd2.mlb.com/components/'

class NotSupportedError(Exception):
    """Exception for a build not being supported"""
    def __init__(self, message):
        Exception.__init__(self, message)

class NotFoundError(Exception):
    """Exception for a resource not being found (e.g. no logs)"""
    def __init__(self, message, location):
        self.location = location
        Exception.__init__(self, ': '.join([message, location]))

class NotImplementedError(Exception):
    """Exception for a feature which is not implemented yet"""
    def __init__(self, message):
        Exception.__init__(self, message)

class TimeoutError(Exception):
    """Exception for a download exceeding the allocated timeout"""
    def __init__(self):
        self.message = 'The download exceeded the allocated timeout'
        Exception.__init__(self, self.message)

# Chunk size when downloading a file
CHUNK_SIZE = 16 * 1024

# http://gd2.mlb.com/components/game/mlb/year_2015/month_05/day_07/gid_2015_05_07_balmlb_nyamlb_1/inning/inning_all.xml

class Scraper(object):
    """Generic class to download an file from the server"""

    def __init__(self, retry_attempts=0, retry_delay=10,
                 timeout=None,
                 log_level='INFO',
                 base_url=None, *args, **kwargs):

        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.refresh = kwargs['refresh']
        self.logger = logging.getLogger('scraper')
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        self.logger.addHandler(ch)
        self.logger.setLevel(logging.INFO)
        self.dest = kwargs['dest']
        if self.dest:
            self.dest = os.path.abspath(self.dest)
            if not os.path.exists(self.dest):
                os.mkdir(self.dest)
        else:
            self.dest = os.path.abspath(os.path.curdir)

    def files(self):
        """Override to provide the list of files your scraper provides."""
        pass

    def download(self):
        """Download the specified file"""

        for file in self.files:

            attempt = 0

            target = os.path.join(self.dest, file['file'])

            # Don't re-download the file unless refreshed
            if os.path.isfile(target):
                if self.refresh:
                    self.logger.info("Redownloading: %s" % file['file'])
                else:
                    self.logger.info("File has already been downloaded: %s" % file['file'])
                    continue

            self.logger.info('Downloading from: %s' %
                             (urllib.unquote(file['url'])))
            self.logger.info('Saving as: %s' % file['file'])

            tmp_file = target + ".part"

            while True:
                attempt += 1
                try:
                    start_time = datetime.now()

                    # Enable streaming mode so we can download content in chunks
                    r = requests.get(file['url'], stream=True)
                    r.raise_for_status()

                    content_length = r.headers.get('Content-length')
                    # ValueError: Value out of range if only total_size given
                    if content_length:
                        total_size = int(content_length.strip())
                        max_value = ((total_size / CHUNK_SIZE) + 1) * CHUNK_SIZE

                    bytes_downloaded = 0

                    log_level = self.logger.getEffectiveLevel()
                    if log_level <= logging.INFO and content_length:
                        widgets = [pb.Percentage(), ' ', pb.Bar(), ' ', pb.ETA(),
                                   ' ', pb.FileTransferSpeed()]
                        pbar = pb.ProgressBar(widgets=widgets,
                                              maxval=max_value).start()

                    with open(tmp_file, 'wb') as f:
                        for chunk in iter(lambda: r.raw.read(CHUNK_SIZE), ''):
                            f.write(chunk)
                            bytes_downloaded += CHUNK_SIZE

                            if log_level <= logging.INFO and content_length:
                                pbar.update(bytes_downloaded)

                            t1 = timedelta.total_seconds(datetime.now() - start_time)
                            if self.timeout and \
                                    t1 >= self.timeout:
                                raise TimeoutError

                    if log_level <= logging.INFO and content_length:
                        pbar.finish()
                    break
                except (requests.exceptions.RequestException, TimeoutError), e:
                    if tmp_file and os.path.isfile(tmp_file):
                        os.remove(tmp_file)
                    if self.retry_attempts > 0:
                        # Log only if multiple attempts are requested
                        self.logger.warning('Download failed: "%s"' % str(e))
                        self.logger.info('Will retry in %s seconds...' %
                                         (self.retry_delay))
                        time.sleep(self.retry_delay)
                        self.logger.info("Retrying... (attempt %s)" % attempt)
                    if attempt >= self.retry_attempts:
                        raise
                    time.sleep(self.retry_delay)

            os.rename(tmp_file, target)

game_url_pattern = re.compile('gid_([\d]+)_([\d]+)_([\d]+)_([a-z]{3})mlb_([a-z]{3})mlb_(\d)/')
GAMES_URL = 'game/mlb/'


class GameScraper(Scraper):
    """Class to download games from a given date from MLB Game Day"""

    def __init__(self, date=None, base_url=None, *args, **kwargs):

        self.date = date

        try:
            if self.date:
                self.date = datetime.strptime(self.date, '%Y-%m-%d')
            else:
                # A date (without time) has been specified. Use yesterday's games since today's are not finished yet.
                self.date = datetime.today() - timedelta(days=1)
            self.date_url = 'year_%d/month_%02d/day_%02d/' % (self.date.year, self.date.month, self.date.day)
        except:
            raise ValueError('%s is not a valid date' % self.date)

        self.base_url = base_url
        if not base_url:
            self.base_url = BASE_URL
        self.base_url = urljoin(self.base_url, GAMES_URL)
        self.base_url = urljoin(self.base_url, self.date_url)

        Scraper.__init__(self, base_url=self.base_url, *args, **kwargs)


    def files(self):
        attempt = 0
        parser = None
        while parser is None:
            attempt += 1
            try:
                # Retrieve all entries from the remote virtual folder
                parser = DirectoryParser(self.base_url,
                                         timeout=self.timeout)
                if not parser.entries:
                    raise NotFoundError('No entries found', self.base_url)

            except (NotFoundError, requests.exceptions.RequestException), e:
                if self.retry_attempts > 0:
                    # Log only if multiple attempts are requested
                    #self.logger.warning("Build not found: '%s'" % e.message)
                    #self.logger.info('Will retry in %s seconds...' %
                    #                 (self.retry_delay))
                    time.sleep(self.retry_delay)
                    #self.logger.info("Retrying... (attempt %s)" % attempt)

                if attempt >= self.retry_attempts:
                    if hasattr(e, 'response') and \
                            e.response.status_code == 404:
                        message = "Specified url has not been found"
                        raise NotFoundError(message, e.response.url)
                    else:
                        raise


        self.files = []
        for entry in parser.entries:
            match = game_url_pattern.match(entry)
            if match:
                file = {}
                file['directory'] = match.group(0)
                file['date'] = self.date
                file['visitor'] = match.group(4)
                file['home'] = match.group(5)
                file['game_no'] = match.group(6)
                file['url'] = urljoin(self.base_url, file['directory'])
                file['url'] = urljoin(self.base_url, file['directory'])
                file['url'] = urljoin(file['url'], 'inning/inning_all.xml')
                file['file'] = os.path.split(file['directory'])[0] + '.xml'

                self.files.append(file)

        return self.files


def cli():
    """Main function for the downloader"""

    usage = 'usage: %prog [options]'
    parser = OptionParser(usage=usage, description=__doc__)
    parser.add_option('--url',
                      dest='url',
                      metavar='URL',
                      help='URL of game directories. Default is known Game Day url.')
    parser.add_option('--retry-attempts',
                      dest='retry_attempts',
                      default=0,
                      type=int,
                      metavar='RETRY_ATTEMPTS',
                      help='Number of times the download will be attempted in '
                           'the event of a failure, default: %default')
    parser.add_option('--retry-delay',
                      dest='retry_delay',
                      default=10.,
                      type=float,
                      metavar='RETRY_DELAY',
                      help='Amount of time (in seconds) to wait between retry '
                           'attempts, default: %default')
    parser.add_option('--timeout',
                      dest='timeout',
                      type=float,
                      metavar='TIMEOUT',
                      help='Amount of time (in seconds) until a download times'
                           ' out')
    parser.add_option('--log-level',
                      action='store',
                      dest='log_level',
                      default='INFO',
                      metavar='LOG_LEVEL',
                      help='Threshold for log output (default: %default)')
    parser.add_option('--date',
                     dest='date',
                     metavar='DATE',
                     help='Date of the games (YYYY-MM-DD), default: yesterday')
    parser.add_option('--refresh',
                      dest='refresh',
                      default=False,
                      metavar='REFRESH',
                      help='Download files even if they already exist (default: %default)')
    parser.add_option('--dest',
                      dest='dest',
                      default='',
                      metavar='DEST',
                      help='Destination directory for downloaded files. Current directory if none specified')

    (options, args) = parser.parse_args()

    # Instantiate scraper and download the build
    scraper_keywords = {'base_url': options.url,
                        'retry_attempts': options.retry_attempts,
                        'retry_delay': options.retry_delay,
                        'timeout': options.timeout,
                        'log_level': options.log_level,
                        'date': options.date,
                        'refresh': options.refresh,
                        'dest': options.dest}

    kwargs = scraper_keywords.copy()

    scraper = GameScraper(**kwargs)

    try:
        scraper.files()
        scraper.download()
    except KeyboardInterrupt:
        print "\nDownload interrupted by the user"

if __name__ == "__main__":
    cli()
