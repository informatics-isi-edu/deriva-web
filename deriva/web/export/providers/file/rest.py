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


class ExportFiles(RestHandler):
    def __init__(self):
        RestHandler.__init__(self, handler_config_file=HANDLER_CONFIG_FILE)

    @web_method()
    def POST(self):
        key, output_dir = create_output_dir()
        file_list = export(config=json.loads(web.data()),
                           base_dir=output_dir,
                           files_only=True,
                           propagate_logs=stob(self.config.get("propagate_logs", False)))
        url_list = list()
        for file_path in file_list.keys():
            url_list.append(''.join([web.ctx.home, web.ctx.path, '/' if not web.ctx.path.endswith("/") else "",
                                     str('%s/%s' % (key, os.path.basename(file_path)))]))

        return self.create_response(url_list)
