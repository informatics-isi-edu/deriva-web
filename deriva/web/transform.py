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
import itertools
import logging
import os
import platform
import requests
import web
from deriva.core import DerivaServer, urlunquote, format_exception
from .core import web_method, RestHandler, RestException, BadRequest

#: logger for the module
logger = logging.getLogger('deriva.web.transform')

#: hostname variable, can be set from env, helpful when testing but not meant for anyone but developers to use
hostname = os.getenv('DERIVA_WEB_TRANSFORM_HOSTNAME', platform.node())

#: server variable, can be manipulated by unit test code, but not meant for any other use
server = DerivaServer('https', hostname)


class PatternTransformer (RestHandler):
    """REST handler for transform processing.
    """
    def __init__(self):
        super(PatternTransformer, self).__init__()

    @web_method()
    def GET(self, catalog_id):
        logger.debug("query: {}".format(web.ctx.query))
        params = [urlunquote(param) for param in web.ctx.query[1:].split('&')]
        logger.debug("params: {}".format(params))
        try:
            return pattern_transformer(catalog_id, params)
        except requests.HTTPError as e:
            raise RestException.from_http_error(e)
        except ValueError as e:
            raise BadRequest(format_exception(e))
        except KeyError as e:
            raise BadRequest(format_exception(e))


def pattern_transformer(catalog_id, params):
    """Performs the transform operation.

    Processes the commands in the order given by the parameters. Supported commands include:
      - `pattern=<format_string>`: use the `<format_string>` for string interpolation based transformation
      - `ermpath=<ermpath_url_fragment>`: get entities for given `<ermpath_url_fragment>`

    Any sequence of the above commands may be processed by the transform operation.

    :param catalog_id: catalog identifier
    :param params: a list of commands
    :return: an iterable of the results
    :raise requests.HTTPError: on failure of ERMrest requests
    :raise ValueError: on bad request parameters
    :raise KeyError: on mismatch between format and ermpath
    """
    catalog = server.connect_ermrest(catalog_id)
    format_string = None
    chain = itertools.chain()

    for param in params:
        if param.startswith('pattern='):
            format_string = param.replace('pattern=', '', 1)
        elif param.startswith('ermpath='):
            ermpath = param.replace('ermpath=', '', 1)
            if not format_string:
                raise ValueError("no 'pattern' specified")

            def _transform(entity):
                _format_string = format_string
                return _format_string.format(catalog=catalog_id, **entity)

            entities = catalog.get(ermpath).json()
            chain = itertools.chain(chain, map(_transform, entities))

    return chain


def web_urls():
    """Returns the web urls for the transform service."""
    return '/transform/format/(^/)+', PatternTransformer
