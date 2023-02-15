#
# Copyright 2016-2023 University of Southern California
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
import json
import flask
from ....core import app, deriva_ctx, deriva_debug, get_client_identity, RestHandler
from ...api import create_output_dir, purge_output_dirs, export, get_client_ip, HANDLER_CONFIG_FILE, \
    DEFAULT_HANDLER_CONFIG
from deriva.core import stob


class ExportBag(RestHandler):
    def __init__(self):
        RestHandler.__init__(self,
                             handler_config_file=HANDLER_CONFIG_FILE,
                             default_handler_config=DEFAULT_HANDLER_CONFIG)

    def POST(self):
        require_authentication = stob(self.config.get("require_authentication", True))
        if require_authentication:
            self.check_authenticated()
        purge_output_dirs(self.config.get("dir_auto_purge_threshold", 5))
        key, output_dir = create_output_dir()
        url = ''.join([web.ctx.home, web.ctx.path, '/' if not web.ctx.path.endswith("/") else "", key])
        params = self.parse_querystr(web.ctx.query)
        public = stob(params.get("public", False))

        # perform the export
        output = export(config=json.loads(web.data().decode()),
                        base_dir=output_dir,
                        service_url=url,
                        public=public,
                        quiet=stob(self.config.get("quiet_logging", False)),
                        propagate_logs=stob(self.config.get("propagate_logs", True)),
                        require_authentication=require_authentication,
                        allow_anonymous_download=stob(self.config.get("allow_anonymous_download", False)),
                        allow_concurrent_export=stob(self.config.get("allow_concurrent_export", False)),
                        max_payload_size_mb=self.config.get("max_payload_size_mb"),
                        timeout=self.config.get("timeout_secs"),
                        dcctx_cid="export/bag",
                        request_ip=get_client_ip())
        output_metadata = list(output.values())[0] or {}

        set_location_header = False
        identifier_landing_page = output_metadata.get("identifier_landing_page")
        if identifier_landing_page:
            url = [identifier_landing_page, url]
            set_location_header = True
        else:
            identifier = output_metadata.get("identifier")
            if identifier:
                url = ["https://identifiers.org/" + identifier, "https://n2t.net/" + identifier, url]
                set_location_header = True

        return self.create_response(url, set_location_header)

@app.route('/export/bdbag', methods=['POST'])
@app.route('/export/bdbag/', methods=['POST'])
def _export_bag_handler():
    if flask.request.method == 'POST':
        return ExportBag().POST()
    else:
        raise NotImplementedError(flask.request.method)


