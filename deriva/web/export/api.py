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
import errno
import logging
import uuid
import web
import shutil
from pathlib import Path
from requests import HTTPError
from deriva.core import urlparse, format_credential, format_exception, get_new_requests_session
from deriva.transfer import GenericDownloader
from deriva.transfer.download import DerivaDownloadAuthenticationError, DerivaDownloadAuthorizationError, \
    DerivaDownloadConfigurationError
from deriva.web.core import STORAGE_PATH, AUTHENTICATION, DEFAULT_HANDLER_CONFIG_DIR, client_has_identity, \
    get_client_identity, get_client_wallet, BadRequest, Unauthorized, Forbidden, Conflict, BadGateway, \
    logger as sys_logger

HANDLER_CONFIG_FILE = os.path.join(DEFAULT_HANDLER_CONFIG_DIR, "export", "export_config.json")
DEFAULT_HANDLER_CONFIG = {
  "propagate_logs": True,
  "quiet_logging": False,
  "allow_anonymous_download": False,
  "max_payload_size_mb": 0,
  "dir_auto_purge_threshold": 5
}

logger = logging.getLogger()


def configure_logging(level=logging.INFO, log_path=None, propagate=True):
    handler = None
    logger.propagate = propagate
    logger.setLevel(level)
    if log_path and propagate:
        handler = logging.FileHandler(log_path)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)

    return handler


def create_output_dir():

    key = str(uuid.uuid4())
    output_dir = os.path.abspath(os.path.join(get_staging_path(), key))
    if not os.path.isdir(output_dir):
        try:
            os.makedirs(output_dir)
        except OSError as error:
            if error.errno != errno.EEXIST:
                raise
    return key, output_dir


def purge_output_dirs(threshold=0, count=1):
    if threshold < 1:
        return
    paths = [os.fspath(path) for path in sorted(
        Path(get_staging_path()).iterdir(), key=os.path.getctime, reverse=True)]
    if not paths or (len(paths) <= threshold):
        return

    for i in range(count):
        try:
            path = paths.pop()
            if os.path.isdir(path):
                shutil.rmtree(path)
        except Exception as e:
            logging.warning(format_exception(e))


def get_staging_path():
    identity = get_client_identity()
    subdir = 'anon-%s' % web.ctx.get("ip", "unknown") if not identity else identity.get('id', '').rsplit("/", 1)[1]
    return os.path.abspath(os.path.join(STORAGE_PATH, "export", subdir or ""))


def get_final_output_path(output_path, output_name=None, ext=''):
    return ''.join([os.path.join(output_path, output_name) if output_name else output_path, ext])


def create_access_descriptor(directory, identity, public=False):
    with open(os.path.abspath(os.path.join(directory, ".access")), 'w') as access:
        access.writelines(''.join([identity if (identity and not public) else "*", '\n']))


def check_access(directory):
    if not AUTHENTICATION:
        return True

    with open(os.path.abspath(os.path.join(directory, ".access")), 'r') as access:
        for identity in access.readlines():
            if client_has_identity(identity.strip()):
                return True
    return False


def export(config=None,
           base_dir=None,
           service_url=None,
           public=False,
           files_only=False,
           quiet=False,
           propagate_logs=True,
           require_authentication=True,
           allow_anonymous_download=False,
           max_payload_size_mb=None):

    log_handler = configure_logging(logging.WARN if quiet else logging.INFO,
                                    log_path=os.path.abspath(os.path.join(base_dir, '.log')),
                                    propagate=propagate_logs)
    try:
        if not config:
            raise BadRequest("No configuration specified.")
        server = dict()
        try:
            # parse host/catalog params
            catalog_config = config["catalog"]
            host = catalog_config["host"]
            if host.startswith("http"):
                url = urlparse(host)
                server["protocol"] = url.scheme
                server["host"] = url.netloc
            else:
                server["protocol"] = "https"
                server["host"] = host
            server["catalog_id"] = catalog_config.get('catalog_id', "1")

            # parse credential params
            token = catalog_config.get("token", None)
            username = catalog_config.get("username", "Anonymous")
            password = catalog_config.get("password", None)

            # sanity-check some bag params
            if "bag" in config:
                if files_only:
                    del config["bag"]
                else:
                    if not config["bag"].get("bag_archiver"):
                        config["bag"]["bag_archiver"] = "zip"

        except (KeyError, AttributeError) as e:
            raise BadRequest('Error parsing configuration: %s' % format_exception(e))

        credentials = None
        session = get_new_requests_session()
        try:
            if token:
                auth_url = ''.join([server["protocol"], "://", server["host"], "/authn/session"])
                session.cookies.set("webauthn", token, domain=server["host"], path='/')
                response = session.get(auth_url)
                response.raise_for_status()
            credentials = format_credential(token=token if token else web.cookies().get("webauthn"),
                                            username=username,
                                            password=password)
        except (ValueError, HTTPError) as e:
            if require_authentication:
                raise Unauthorized(format_exception(e))
        finally:
            if session:
                session.close()
                del session

        try:
            identity = get_client_identity()
            user_id = username if not identity else identity.get('display_name', identity.get('id'))
            create_access_descriptor(base_dir, identity=None if not identity else identity.get('id'), public=public)
            wallet = get_client_wallet()
        except (KeyError, AttributeError) as e:
            raise BadRequest(format_exception(e))

        try:
            sys_logger.info("Creating export at [%s] on behalf of user: %s" % (base_dir, user_id))
            envars = {GenericDownloader.SERVICE_URL_KEY: service_url} if service_url else None
            downloader = GenericDownloader(server=server,
                                           output_dir=base_dir,
                                           envars=envars,
                                           config=config,
                                           credentials=credentials,
                                           allow_anonymous=allow_anonymous_download,
                                           max_payload_size_mb=max_payload_size_mb)
            return downloader.download(identity=identity, wallet=wallet)
        except DerivaDownloadAuthenticationError as e:
            raise Unauthorized(format_exception(e))
        except DerivaDownloadAuthorizationError as e:
            raise Forbidden(format_exception(e))
        except DerivaDownloadConfigurationError as e:
            raise Conflict(format_exception(e))
        except Exception as e:
            raise BadGateway(format_exception(e))

    finally:
        if log_handler:
            logger.removeHandler(log_handler)
