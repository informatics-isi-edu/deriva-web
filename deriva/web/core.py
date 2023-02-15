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
"""Core service logic and dispatch rules for Deriva REST API

"""

import os
import sys
import logging
import traceback
import werkzeug
import flask
import json
import random
import base64
import datetime
import pytz
import struct
import urllib
import requests
from collections import OrderedDict
from logging.handlers import SysLogHandler
import webauthn2.util
from webauthn2.util import deriva_ctx, deriva_debug, merge_config, negotiated_content_type, Context, context_from_environment
from webauthn2.manager import Manager
from webauthn2.rest import format_trace_json, format_final_json
from deriva.core import format_exception

SERVICE_BASE_DIR = os.path.expanduser("~")
STORAGE_BASE_DIR = os.path.join("deriva", "data")

DEFAULT_CONFIG = {
    "storage_path": os.path.abspath(os.path.join(SERVICE_BASE_DIR, STORAGE_BASE_DIR)),
    "authentication": None,
    "404_html": "<html><body><h1>Resource Not Found</h1><p>The requested resource could not be found at this location."
                "</p><p>Additional information:</p><p><pre>%(message)s</pre></p></body></html>",
    "403_html": "<html><body><h1>Access Forbidden</h1><p>%(message)s</p></body></html>",
    "401_html": "<html><body><h1>Authentication Required</h1><p>%(message)s</p></body></html>",
    "400_html": "<html><body><h1>Bad Request</h1><p>One or more request parameters are incorrect. "
                "</p><p>Additional information:</p><p><pre>%(message)s</pre></p></body></html>",
}
DEFAULT_CONFIG_FILE = os.path.abspath(os.path.join(SERVICE_BASE_DIR, 'deriva_config.json'))
DEFAULT_HANDLER_CONFIG_DIR = os.path.abspath(os.path.join(SERVICE_BASE_DIR, 'conf.d'))

SERVICE_CONFIG = dict()
if os.path.isfile(DEFAULT_CONFIG_FILE):
    SERVICE_CONFIG = merge_config(jsonFileName=DEFAULT_CONFIG_FILE)
else:
    SERVICE_CONFIG = merge_config(defaults=DEFAULT_CONFIG)

STORAGE_PATH = SERVICE_CONFIG.get('storage_path')

# instantiate webauthn2 manager if using webauthn
AUTHENTICATION = SERVICE_CONFIG.get("authentication", None)
webauthn2_manager = Manager() if AUTHENTICATION == "webauthn" else None

# setup logger and web request log helpers
logger = logging.getLogger()
logger.setLevel(logging.INFO)
try:
    # the use of '/dev/log' causes SysLogHandler to assume the availability of Unix sockets
    sysloghandler = SysLogHandler(address='/dev/log', facility=SysLogHandler.LOG_LOCAL1)
except:
    # this fallback allows this file to at least be cleanly imported on non-Unix systems
    sysloghandler = logging.StreamHandler()
syslogformatter = logging.Formatter('deriva.web[%(process)d.%(thread)d]: %(message)s')
sysloghandler.setFormatter(syslogformatter)
logger.addHandler(sysloghandler)


# the Flask app we will configure with routes
app = flask.Flask(__name__)


def log_parts():
    """Generate a dictionary of interpolation keys used by our logging template."""
    return get_log_parts('derivaweb_start_time',
                         'derivaweb_request_guid',
                         'derivaweb_request_content_range',
                         'derivaweb_content_type')


def request_trace(tracedata):
    """Log one tracedata event as part of a request's audit trail.

       tracedata: a string representation of trace event data
    """
    logger.info(format_trace_json(
        tracedata,
        start_time=deriva_ctx.derivaweb_start_time,
        req=deriva_ctx.derivaweb_request_guid,
        client=flask.request.remote_addr,
        webauthn2_context=deriva_ctx.webauthn2_context,
    ))

class RestException(webauthn2.util.RestException):

    def __init__(self, message=None, headers={}):
        if message is None:
            message = self.description
        else:
            message = '%s Detail: %s' % (self.description, message)
        super(RestException, self).__init__(message, headers=headers)

    @classmethod
    def from_http_error(cls, e):
        """Translates a requests.HTTPError into a RestException.

        :param e: a requests.HTTPError instance
        :return: a RestException based on the input error
        """
        assert isinstance(e, requests.HTTPError), "Expected 'requests.HTTPError' object"
        r = e.response
        if r.status_code == 400:
            raise BadRequest(format_exception(e))
        elif r.status_code == 401:
            raise Unauthorized(format_exception(e))
        elif r.status_code == 403:
            raise Forbidden(format_exception(e))
        elif r.status_code == 404:
            raise NotFound(format_exception(e))
        elif r.status_code == 405:
            raise NoMethod(format_exception(e))
        elif r.status_code == 409:
            raise Conflict(format_exception(e))
        elif r.status_code == 411:
            raise LengthRequired(format_exception(e))
        elif r.status_code == 412:
            raise PreconditionFailed(format_exception(e))
        elif r.status_code == 416:
            raise BadRange(format_exception(e))
        elif r.status_code == 500:
            raise InternalServerError(format_exception(e))
        elif r.status_code == 501:
            raise NotImplemented(format_exception(e))
        elif r.status_code == 502:
            raise BadGateway(format_exception(e))
        else:
            logger.error(
                'Unhandled HTTPError status code {sc} -- {msg}.'.format(sc=r.status_code, msg=format_exception(e)))
            raise InternalServerError(format_exception(e))


class NotModified(RestException):
    code = 304
    message = 'Resource not modified.'


class BadRequest(RestException):
    code = 400
    message = 'Request malformed.'


class Unauthorized(RestException):
    code = 401
    message = 'Access requires authentication.'


class Forbidden(RestException):
    code = 403
    message = 'Access forbidden.'


class NotFound(RestException):
    code = 404
    message = 'Resource not found.'


class NoMethod(RestException):
    code = 405
    message = 'Request method not allowed on this resource.'


class Conflict(RestException):
    code = 409
    message = 'Request conflicts with state of server.'


class LengthRequired(RestException):
    code = 411
    message = 'Content-Length header is required for this request.'


class PreconditionFailed(RestException):
    code = 412
    message = 'Resource state does not match requested preconditions.'


class BadRange(RestException):
    code = 416
    message = 'Requested Range is not satisfiable for this resource.'

    def __init__(self, msg=None, headers=None, nbytes=None):
        RestException.__init__(self, msg, headers)
        if nbytes is not None:
            self.headers['content-range'] = 'bytes */%d' % nbytes


class InternalServerError(RestException):
    code = 500
    message = 'A processing error prevented the server from fulfilling this request.'


class NotImplemented(RestException):
    code = 501
    message = 'Request not implemented for this resource.'


class BadGateway(RestException):
    code = 502
    message = 'A downstream processing error prevented the server from fulfilling this request.'


def client_has_identity(identity):
    if identity == "*":
        return True
    if deriva_ctx.webauthn2_context.attributes is not None:
        for attrib in deriva_ctx.webauthn2_context.attributes:
            if attrib['id'] == identity:
                return True
    return False


def get_client_identity():
    if deriva_ctx.webauthn2_context and deriva_ctx.webauthn2_context.client:
        return deriva_ctx.webauthn2_context.client
    else:
        return None


def get_client_wallet():
    if deriva_ctx.webauthn2_context and deriva_ctx.webauthn2_context.extra_values:
        return deriva_ctx.webauthn2_context.extra_values.get("wallet")
    else:
        return None

@app.before_request
def before_request():
    # request context init
    deriva_ctx.derivaweb_request_guid = base64.b64encode(struct.pack('Q', random.getrandbits(64))).decode()
    deriva_ctx.derivaweb_start_time = datetime.datetime.now(pytz.timezone('UTC'))
    deriva_ctx.deriva_response = flask.Response() # to accumulate response content by side-effect
    deriva_ctx.derivaweb_request_content_range = '-/-'
    deriva_ctx.derivaweb_content_type = None
    deriva_ctx.derivaweb_request_error_detail = None
    deriva_ctx.derivaweb_request_trace = request_trace
    deriva_ctx.webauthn2_manager = webauthn2_manager

    # call directly into manager code to access full session context from DB
    # we may need the extra_values wallet info, not passed from mod_webauthn!
    deriva_ctx.webauthn2_context = webauthn2_manager.get_request_context(
        require_client=False,
        require_attributes=False,
    ) if webauthn2_manager is not None else Context()

@app.after_request
def after_request(response):
    if response is deriva_ctx.deriva_response:
        # normal flow where we are returning our accumulated response
        pass
    elif isinstance(response, flask.Response):
        # flask generated a different response for us!
        deriva_ctx.deriva_response = response
    elif isinstance(response, werkzeug.exceptions.HTTPException):
        deriva_ctx.deriva_response.status = respnse.code

    deriva_ctx.deriva_content_type = response.headers.get('content-type', 'none')
    if 'content-range' in response.headers:
        content_range = response.headers['content-range']
        if content_range.startswith('bytes '):
            content_range = content_range[6:]
        deriva_ctx.derivaweb_request_content_range = content_range
    elif 'content-length' in response.headers:
        deriva_ctx.derivaweb_request_content_range = '*/%s' % response.headers['content-length']
    else:
        deriva_ctx.derivaweb_request_content_range = '*/0'

    logger.info(format_final_json(
        environ=flask.request.environ,
        webauthn2_context=deriva_ctx.webauthn2_context,
        req=deriva_ctx.derivaweb_request_guid,
        start_time=deriva_ctx.derivaweb_start_time,
        client=flask.request.remote_addr,
        status=deriva_ctx.deriva_response.status,
        content_range=deriva_ctx.derivaweb_request_content_range,
        content_type=deriva_ctx.derivaweb_content_type,
        track=(deriva_ctx.webauthn2_context.tracking if deriva_ctx.webauthn2_context else None),
    ))
    return response

@app.errorhandler(Exception)
def error_handler(ev):
    if isinstance(ev, werkzeug.exceptions.HTTPException):
        deriva_debug('got HTTPException in derivaweb request handler: %s' % ev)
        deriva_ctx.deriva_request_error_detail = ev.description
    else:
        et, ev2, tb = sys.exc_info()
        deriva_debug(
            'Got unhandled exception in derivaweb request handler: %s\n%s\n',
            ev,
            ''.join(traceback.format_exception(et, ev2, tb)),
        )
        ev = InternalServerError(str(ev))

    return ev

class RestHandler(object):
    """Generic implementation logic for deriva REST API handlers.

    """

    def __init__(self, handler_config_file=None, default_handler_config=None):
        self.get_body = True
        self.http_etag = None
        self.http_vary = webauthn2_manager.get_http_vary() if webauthn2_manager else None
        self.config = self.load_handler_config(handler_config_file, default_handler_config)
        # deriva_debug("Using configuration: %s" % json.dumps(self.config))

    def load_handler_config(self, config_file, default_config=None):
        config = default_config.copy() if default_config else {}
        if config_file and os.path.isfile(config_file):
            with open(config_file) as cf:
                config.update(json.load(cf))
        return config

    def check_authenticated(self):
        # Ensure authenticated by checking for a populated client identity, otherwise raise 401
        if AUTHENTICATION == "webauthn" and not (deriva_ctx.webauthn2_context and deriva_ctx.webauthn2_context.client):
            raise Unauthorized()

    def trace(self, msg):
        deriva_ctx.deriva_request_trace(msg)

    def parse_querystr(self, querystr):
        if querystr.startswith("?"):
            querystr = querystr.lstrip("?")
        params = querystr.split('&')
        result = {}
        for param in params:
            if param:
                parts = param.split('=')
                if parts:
                    result[parts[0]] = '='.join(parts[1:])
        return result

    def get_content(self, file_path):
        get_body = flask.request.method.upper() != 'HEAD'

        deriva_ctx.deriva_response.status = '200 OK'
        nbytes = os.path.getsize(file_path)
        deriva_ctx.deriva_response.content_length = nbytes

        if not get_body:
            return deriva_ctx.deriva_response

        f = open(file_path, 'rb')
        deriva_ctx.deriva_response.response = f
        deriva_ctx.deriva_response.direct_passthrough = True
        return deriva_ctx.deriva_response

    def create_response(self, urls, set_location_header=True):
        """Form response for resource creation request."""
        deriva_ctx.deriva_response.status = '201 Created'
        deriva_ctx.deriva_response.content_type = 'text/uri-list'
        if isinstance(urls, list):
            location = urls[0]
            body = '\n'.join(urls)
        else:
            location = body = urls
        if set_location_header:
            deriva_ctx.deriva_response.location = location
        deriva_ctx.deriva_response.content_length = len(body)
        deriva_ctx.deriva_response.set_data(body)
        return deriva_ctx.deriva_response

    def delete_response(self):
        """Form response for deletion request."""
        deriva_ctx.deriva_response.status = '204 No Content'
        return deriva_ctx.deriva_response

    def update_response(self):
        """Form response for update request."""
        deriva_ctx.deriva_response.status = '204 No Content'
        return deriva_ctx.deriva_response
