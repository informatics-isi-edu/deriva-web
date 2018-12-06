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
import os
import json
import web
from deriva.web.core import web_method, RestHandler
from deriva.web.export.api import create_output_dir, export, HANDLER_CONFIG_FILE
from deriva.core import stob
from deriva.transfer import GenericDownloader


class ExportFiles(RestHandler):
    def __init__(self):
        RestHandler.__init__(self, handler_config_file=HANDLER_CONFIG_FILE)

    @web_method()
    def POST(self):
        key, output_dir = create_output_dir()
        url = ''.join([web.ctx.home, web.ctx.path, '/' if not web.ctx.path.endswith("/") else "", key])
        params = self.parse_querystr(web.ctx.query)
        public = stob(params.get("public", False))

        # perform the export
        output = export(config=json.loads(web.data()),
                        base_dir=output_dir,
                        service_url=url,
                        files_only=True,
                        public=public,
                        quiet=stob(self.config.get("quiet_logging", False)),
                        propagate_logs=stob(self.config.get("propagate_logs", True)))
        uri_list = list()
        set_location_header = False if len(output.keys()) > 1 else True
        for file_path, file_metadata in output.items():
            remote_paths = file_metadata.get(GenericDownloader.REMOTE_PATHS_KEY)
            if remote_paths:
                target_url = remote_paths[0]
            else:
                target_url = ''.join([url, str('/%s' % file_path)])
            uri_list.append(target_url)

        return self.create_response(uri_list, set_location_header)
