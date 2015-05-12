#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import urllib
import requests
import logging
from datetime import datetime, timedelta
import progressbar as pb

class TimeoutError(Exception):
    """Exception for a download exceeding the allocated timeout"""
    def __init__(self):
        self.message = 'The download exceeded the allocated timeout'
        Exception.__init__(self, self.message)

# Chunk size when downloading a file
CHUNK_SIZE = 16 * 1024

class GameDayFile(object):

    def __init__(self, directory=None, url=None, file=None, logger=None):
        self.url = url
        self.file = file
        self.directory = directory
        self.logger = logger

    def download(self, dest=None, refresh=False, timeout=None):
        attempt = 0

        target = os.path.join(dest, self.file)

        # Don't re-download the file unless refreshed
        if os.path.isfile(target):
            if refresh:
                self.logger.info("Redownloading: %s" % self.file)
            else:
                self.logger.info("File has already been downloaded: %s" % self.file)
                return

        self.logger.info('Downloading from: %s' %
                         (urllib.unquote(self.file)))
        self.logger.info('Saving as: %s' % self.file)

        tmp_file = target + ".part"

        while True:
            attempt += 1
            try:
                start_time = datetime.now()

                # Enable streaming mode so we can download content in chunks
                r = requests.get(self.url, stream=True)
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
                        if timeout and t1 >= timeout:
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

    def parse(self):
        pass

    def populate(self):
        pass

class GameDayGame(GameDayFile):

    def __init__(self, directory=None, url=None, file=None, date=None, visitor=None, home=None, game_no=None, logger=None):
        self.date = date
        self.visitor = visitor
        self.home = home
        self.game_no = game_no
        GameDayFile.__init__(self, url=url, file=file, directory=directory, logger=logger)

