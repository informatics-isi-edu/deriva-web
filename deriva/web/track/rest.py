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
import requests
import web
from ..core import web_method, RestHandler, RestException, BadRequest
from . import api

import itertools
from deriva.core import DerivaServer, urlunquote


class CustomTracks (RestHandler):
    """REST handler for custom tracks.
    """
    def __init__(self):
        super(CustomTracks, self).__init__(handler_config_file=api.HANDLER_CONFIG_FILE,
                                           default_handler_config=api.DEFAULT_CONFIG)

    @web_method()
    def GET(self, catalog_id, schema, table, rids, assembly=None):
        try:
            return api.create_custom_tracks_content(self.config, catalog_id, schema, table, rids, assembly)
        except requests.HTTPError as e:
            raise RestException.from_http_error(e)


class TrackDescription (RestHandler):
    """REST handler for track description.
    """
    def __init__(self):
        super(TrackDescription, self).__init__(handler_config_file=api.HANDLER_CONFIG_FILE,
                                               default_handler_config=api.DEFAULT_CONFIG)

    @web_method()
    def GET(self, catalog_id, schema, table, rid):
        try:
            return api.create_track_description_content(self.config, catalog_id, schema, table, rid)
        except requests.HTTPError as e:
            raise RestException.from_http_error(e)


class TrackLine (RestHandler):
    """REST handler for custom tracks.
    """
    def __init__(self):
        super(TrackLine, self).__init__(
            handler_config_file=api.HANDLER_CONFIG_FILE, default_handler_config=api.DEFAULT_CONFIG)

    @web_method()
    def GET(self):
        print(web.ctx.query)
        params = web.ctx.query[1:].split('&')
        print(params)
        try:
            return self.process_track_line_params(self.config, params)
        except requests.HTTPError as e:
            raise RestException.from_http_error(e)

    def process_track_line_params(self, config, params):
        server = DerivaServer('https', config['hostname'])
        catalog = None
        chain = itertools.chain()
        track_line_pattern = config['track_line_pattern']

        for param in params:
            if param.startswith('catalog='):
                catalog_id = param.replace('catalog=', '', 1)
                print('catalog id', catalog_id)
                catalog = server.connect_ermrest(catalog_id)
            elif param.startswith('ermpath='):
                if not catalog:
                    raise BadRequest()
                ermpath = param.replace('ermpath=', '', 1)
                ermpath = urlunquote(ermpath)
                print('unquoted ermpath', ermpath)
                chain = itertools.chain(chain, catalog.get(ermpath))

        return chain
