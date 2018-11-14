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
    """This test suite requires a valid endpoint that can satisfy the ermpath requests."""

    def test_basic(self):
        params = [
            'catalog=1',
            'format=track type={type} name="{RID}" description="{filename}" bigDataUrl={url}\n',
            'ermpath=/attribute/D:=isa:dataset/RID=TMJ/T:=isa:track_data/mapping_assembly=FACEBASE%3A1-4FZE/FF:=vocab:file_format/$T/RID,filename,url,type:=FF:name'
        ]
        results = transform.transformer(params)
        results = [result for result in results]
        self.assertIsNotNone(results)
        self.assertGreater(len(results), 0)
