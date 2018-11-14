#
# Copyright 2018 University of Southern California
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
import unittest
from deriva.web import transform


class TestTransform (unittest.TestCase):
    """This is a work in progress."""

    def test_basic(self):
        params = 'catalog=1&format=track%20type%3D%7BType%7D%20name%3D%22%7BName%7D%22%20description%3D%22%7BDescription%7D%22%20bigDataUrl%3D%7BURL%7D%5Cn&ermpath=%2Fattribute%2FD%3A%3Disa%3Adataset%2FRID%3DTMJ%2FT%3A%3Disa%3Atrack_data%2Fmapping_assembly%3DFACEBASE%253A1-4FZE%2FFF%3A%3Dvocab%3Afile_format%2F%24T%2FContainer_RID%3A%3DD%3ARID%2CRID%2CName%3A%3DRID%2CDescription%3A%3Dfilename%2CType%3A%3DFF%3Aname%2CURL%3A%3Durl'
        params = params.split('&')
        results = transform.transform(params)
        results = [result for result in results]
        self.assertIsNotNone(results)
        self.assertGreater(len(results), 0)
