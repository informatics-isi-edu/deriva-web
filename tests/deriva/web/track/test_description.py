#
# Copyright 2016 University of Southern California
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Extremely minimal tests of the track service.

You must set env var 'DERIVA_WEB_TRACK_TEST_HOST' to the appropriate hostname for these tests. In the present form,
this is really only useful for the developers of this service.
"""
import os
import unittest
from deriva.web.track import rest, api

ENV_DERIVA_WEB_TRACK_TEST_HOST = 'DERIVA_WEB_TRACK_TEST_HOST'
DERIVA_WEB_TRACK_TEST_HOST = os.getenv(ENV_DERIVA_WEB_TRACK_TEST_HOST, None)
api.DEFAULT_CONFIG['hostname'] = DERIVA_WEB_TRACK_TEST_HOST


@unittest.skipIf(not DERIVA_WEB_TRACK_TEST_HOST, '{} not defined'.format(ENV_DERIVA_WEB_TRACK_TEST_HOST))
class TestTrackDescription (unittest.TestCase):
    """Extremely minimal tests.
    """
    def test_description(self):
        td = rest.TrackDescription()
        results = api.create_track_description_content(td.config, 1, 'isa', 'experiment', '3406')
        self.assertIsNotNone(results)
        self.assertGreater(len(results), 0)
