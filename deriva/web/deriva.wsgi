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

import os
from deriva.web.app import app
from werkzeug.middleware.proxy_fix import ProxyFix

if os.environ.get("DERIVA_WSGI_RPROXY", "").lower() in {"1", "true", "yes"}:
    application = ProxyFix(app, x_for=1, x_proto=1, x_host=1)
else:
    application = app
