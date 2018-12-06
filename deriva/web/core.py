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
"""Core service logic and dispatch rules for Deriva REST API

"""

import os
import logging
import web
import json
import random
import base64
import datetime
import pytz
import webauthn2
import struct
import urllib
import requests
from collections import OrderedDict
from logging.handlers import SysLogHandler
from webauthn2.util import merge_config, context_from_environment
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
webauthn2_manager = webauthn2.Manager() if AUTHENTICATION == "webauthn" else None

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


def log_parts():
    """Generate a dictionary of interpolation keys used by our logging template."""
    now = datetime.datetime.now(pytz.timezone('UTC'))
    elapsed = (now - web.ctx.deriva_start_time)
    client_identity_obj = web.ctx.webauthn2_context and web.ctx.webauthn2_context.client or None
    parts = dict(
        elapsed=elapsed.seconds + 0.001 * (elapsed.microseconds / 1000),
        client_ip=web.ctx.ip,
        client_identity_obj=client_identity_obj,
        reqid=web.ctx.deriva_request_guid
    )
    return parts


def request_trace(tracedata):
    """Log one tracedata event as part of a request's audit trail.

       tracedata: a string representation of trace event data
    """
    parts = log_parts()
    od = OrderedDict([
        (k, v) for k, v in [
            ('elapsed', parts['elapsed']),
            ('req', parts['reqid']),
            ('trace', tracedata),
            ('client', parts['client_ip']),
            ('user', parts['client_identity_obj']),
        ]
        if v
    ])
    logger.info(json.dumps(od, separators=(', ', ':')).encode('utf-8'))


class RestException(web.HTTPError):
    message = None
    status = None
    headers = {
        'Content-Type': 'text/plain'
    }

    def __init__(self, message=None, headers=None):
        if headers:
            hdr = dict(self.headers)
            hdr.update(headers)
        else:
            hdr = self.headers
        msg = message or self.message
        web.HTTPError.__init__(self, self.status, hdr, msg + '\n')

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
    status = '304 Not Modified'
    message = 'Resource not modified.'


class TemplatedRestException(RestException):
    error_type = ''
    supported_content_types = ['text/plain', 'text/html']

    def __init__(self, message=None, headers=None):
        # filter types to those for which we have a response template, or text/plain which we always support
        supported_content_types = [
            content_type for content_type in self.supported_content_types
            if "%s_%s" % (
                self.error_type, content_type.split('/')[-1]) in SERVICE_CONFIG or content_type == 'text/plain'
        ]
        default_content_type = supported_content_types[0]
        # find client's preferred type
        content_type = webauthn2.util.negotiated_content_type(supported_content_types, default_content_type)
        # lookup template and use it if available
        template_key = '%s_%s' % (self.error_type, content_type.split('/')[-1])
        if template_key in SERVICE_CONFIG:
            message = SERVICE_CONFIG[template_key] % dict(message=message)
        header = {'Content-Type': content_type}
        headers = headers.update(header) if headers else header
        RestException.__init__(self, message, headers)
        web.header('Content-Type', content_type)


class BadRequest(TemplatedRestException):
    error_type = '400'
    status = '400 Bad Request'
    message = 'Request malformed.'


class Unauthorized(TemplatedRestException):
    error_type = '401'
    status = '401 Unauthorized'
    message = 'Access requires authentication.'


class Forbidden(TemplatedRestException):
    error_type = '403'
    status = '403 Forbidden'
    message = 'Access forbidden.'


class NotFound(TemplatedRestException):
    error_type = '404'
    status = '404 Not Found'
    message = 'Resource not found.'


class NoMethod(RestException):
    status = '405 Method Not Allowed'
    message = 'Request method not allowed on this resource.'


class Conflict(RestException):
    status = '409 Conflict'
    message = 'Request conflicts with state of server.'


class LengthRequired(RestException):
    status = '411 Length Required'
    message = 'Content-Length header is required for this request.'


class PreconditionFailed(RestException):
    status = '412 Precondition Failed'
    message = 'Resource state does not match requested preconditions.'


class BadRange(RestException):
    status = '416 Requested Range Not Satisfiable'
    message = 'Requested Range is not satisfiable for this resource.'

    def __init__(self, msg=None, headers=None, nbytes=None):
        RestException.__init__(self, msg, headers)
        if nbytes is not None:
            web.header('Content-Range', 'bytes */%d' % nbytes)


class InternalServerError(RestException):
    status = '500 Internal Server Error'
    message = 'A processing error prevented the server from fulfilling this request.'


class NotImplemented(RestException):
    status = '501 Not Implemented'
    message = 'Request not implemented for this resource.'


class BadGateway(RestException):
    status = '502 Bad Gateway'
    message = 'A downstream processing error prevented the server from fulfilling this request.'


def client_has_identity(identity):
    if identity == "*":
        return True
    get_client_auth_context()
    for attrib in web.ctx.webauthn2_context.attributes:
        if attrib['id'] == identity:
            return True
    return False


def get_client_identity():
    get_client_auth_context()
    if web.ctx.webauthn2_context and web.ctx.webauthn2_context.client:
        return web.ctx.webauthn2_context.client
    else:
        return None


def get_client_wallet():
    get_client_auth_context(from_environment=False)
    if web.ctx.webauthn2_context and web.ctx.webauthn2_context.extra_values:
        return web.ctx.webauthn2_context.extra_values.get("wallet")
    else:
        return None


def get_client_auth_context(from_environment=True, fallback=True):

    try:
        if from_environment:
            web.ctx.webauthn2_context = context_from_environment()
            if web.ctx.webauthn2_context is not None and web.ctx.webauthn2_context.client is not None:
                return
            if fallback:
                web.debug(
                    "falling back to webauthn2_manager.get_request_context() after failed context_from_environment()")
        else:
            fallback = True
        if fallback:
            web.ctx.webauthn2_context = webauthn2_manager.get_request_context() if webauthn2_manager else None
    except (ValueError, IndexError) as e:
        web.debug("Exception getting client authentication context: %s" % str(e))
        raise Unauthorized("The requested service requires client authentication.")


def web_method():
    """Augment web handler method with common service logic."""

    def helper(original_method):
        def wrapper(*args):
            # request context init
            web.ctx.deriva_request_guid = base64.b64encode(struct.pack('Q', random.getrandbits(64)))
            web.ctx.deriva_start_time = datetime.datetime.now(pytz.timezone('UTC'))
            web.ctx.deriva_request_content_range = '-/-'
            web.ctx.deriva_request_error_detail = None
            web.ctx.deriva_content_type = None
            web.ctx.webauthn2_manager = webauthn2_manager
            web.ctx.webauthn2_context = webauthn2.Context()  # set empty context for sanity
            web.ctx.deriva_request_trace = request_trace

            # get client authentication context
            get_client_auth_context(fallback=False)
            try:
                # run actual method
                return original_method(*args)
            except web.HTTPError as e:
                web.ctx.deriva_request_error_detail = e.data
                raise
            except Exception as e:
                web.ctx.deriva_request_error_detail = str(e)
                raise
            finally:
                # finalize
                parts = log_parts()
                session = web.ctx.webauthn2_context.session if web.ctx.webauthn2_context else None
                if session is None or isinstance(session, dict):
                    pass
                else:
                    session = session.to_dict()

                try:
                    dcctx = web.ctx.env.get('HTTP_DERIVA_CLIENT_CONTEXT', 'null')
                    dcctx = urllib.unquote(dcctx)
                    dcctx = json.loads(dcctx)
                except:
                    dcctx = None

                od = OrderedDict([
                    (k, v) for k, v in [
                        ('elapsed', parts['elapsed']),
                        ('req', parts['reqid']),
                        ('scheme', web.ctx.protocol),
                        ('host', web.ctx.host),
                        ('status', web.ctx.status),
                        ('detail', web.ctx.deriva_request_error_detail),
                        ('method', web.ctx.method),
                        ('path', web.ctx.env['REQUEST_URI']),
                        ('range', web.ctx.deriva_request_content_range),
                        ('type', web.ctx.deriva_content_type),
                        ('client', parts['client_ip']),
                        ('user', parts['client_identity_obj']),
                        ('referrer', web.ctx.env.get('HTTP_REFERER')),
                        ('agent', web.ctx.env.get('HTTP_USER_AGENT')),
                        ('session', session),
                        ('track', web.ctx.webauthn2_context.tracking if web.ctx.webauthn2_context else None),
                        ('dcctx', dcctx),
                    ]
                    if v
                ])
                logger.info(json.dumps(od, separators=(', ', ':')).encode('utf-8'))

        return wrapper

    return helper


class RestHandler(object):
    """Generic implementation logic for deriva REST API handlers.

    """

    def __init__(self, handler_config_file=None, default_handler_config=None):
        self.get_body = True
        self.http_etag = None
        self.http_vary = webauthn2_manager.get_http_vary() if webauthn2_manager else None
        self.config = self.load_handler_config(handler_config_file, default_handler_config)

    def load_handler_config(self, config_file, default_config=None):
        config = default_config.copy() if default_config else {}
        if config_file and os.path.isfile(config_file):
            with open(config_file) as cf:
                config.update(json.load(cf))
        return config

    def trace(self, msg):
        web.ctx.deriva_request_trace(msg)

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

    def get_content(self, file_path, get_body=True):

        web.ctx.status = '200 OK'
        nbytes = os.path.getsize(file_path)
        web.header('Content-Length', nbytes)

        if not get_body:
            return

        try:
            f = open(file_path, 'rb')
            return f.read()
        except Exception as e:
            raise NotFound(e)

    def create_response(self, urls, set_location_header=True):
        """Form response for resource creation request."""
        web.ctx.status = '201 Created'
        web.header('Content-Type', 'text/uri-list')
        if isinstance(urls, list):
            location = urls[0]
            body = '\n'.join(urls)
        else:
            location = body = urls
        if set_location_header:
            web.header('Location', location)
        web.header('Content-Length', len(body))
        return body

    def delete_response(self):
        """Form response for deletion request."""
        web.ctx.status = '204 No Content'
        return ''

    def update_response(self):
        """Form response for update request."""
        web.ctx.status = '204 No Content'
        return ''

    @web_method()
    def HEAD(self, *args):
        """Get resource metadata."""
        self.get_body = False
        if hasattr(self, 'GET'):
            return self.GET(*args)
        else:
            raise NoMethod('Method HEAD not supported for this resource.')

