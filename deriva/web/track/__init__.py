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
"""DERIVA Web service for UCSC Genome Browser protocol.
"""
from deriva.web.track.rest import CustomTracks, TrackDescription, TrackLine


def web_urls():
    """Builds and returns the web_urls for web.py.
    """
    urls = (
        '/track/custom/([^/]+)/([^/:]+):([^/:]+)/RID=([^/]+)', CustomTracks,
        '/track/custom/([^/]+)/([^/:]+):([^/:]+)/RID=([^/]+)/Genome_Assembly=([^/]+)', CustomTracks,
        '/track/description/([^/]+)/([^/:]+):([^/:]+)/RID=([^/]+)', TrackDescription,
        '/track/line', TrackLine
    )
    return tuple(urls)
