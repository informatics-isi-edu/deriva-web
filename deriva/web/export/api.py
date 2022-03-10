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
import socket
from pathlib import Path
from portalocker import LockException, AlreadyLocked
from requests import HTTPError
from deriva.core import urlparse, format_credential, format_exception, get_new_requests_session, lock_file
from deriva.transfer import GenericDownloader
from deriva.transfer.download import DerivaDownloadAuthenticationError, DerivaDownloadAuthorizationError, \
    DerivaDownloadConfigurationError, DerivaDownloadTimeoutError, DerivaDownloadError
from deriva.web.core import STORAGE_PATH, AUTHENTICATION, DEFAULT_HANDLER_CONFIG_DIR, client_has_identity, \
    get_client_identity, get_client_wallet, BadRequest, Unauthorized, Forbidden, Conflict, BadGateway, \
    logger as sys_logger

HANDLER_CONFIG_FILE = os.path.join(DEFAULT_HANDLER_CONFIG_DIR, "export", "export_config.json")
DEFAULT_HANDLER_CONFIG = {
  "propagate_logs": True,
  "quiet_logging": False,
  "require_authentication": True,
  "allow_anonymous_download": False,
  "allow_concurrent_download": False,
  "max_payload_size_mb": 0,
  "dir_auto_purge_threshold": 5,
  "timeout_secs": 600
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
    basedir = get_staging_path()
    if not os.path.isdir(basedir):
        return
    paths = [os.fspath(path) for path in sorted(Path(basedir).iterdir(), key=os.path.getctime, reverse=True)]
    if not paths or (len(paths) < threshold):
        return

    for i in range(count):
        try:
            path = paths.pop()
            if os.path.isdir(path):
                shutil.rmtree(path)
        except Exception as e:
            logging.warning(format_exception(e))


def get_client_ip():
    ip = web.ctx.env.get('HTTP_X_FORWARDED_FOR', web.ctx.get('ip', ''))
    for ip in ip.split(','):
        ip = ip.strip()
        try:
            socket.inet_aton(ip)
            return ip
        except socket.error:
            pass
    return None


def get_staging_path():
    identity = get_client_identity()
    subdir = 'anon-%s' % get_client_ip() or "unknown" \
        if not identity else identity.get('id', '').rsplit("/", 1)[1]
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


def get_bearer_token(header):
    if not header:
        return None
    bearer, _, token = header.partition(' ')
    return token if bearer == 'Bearer' else None


def get_lockfile_path():
    directory = get_staging_path()
    lockfile = os.path.abspath(os.path.join(directory, ".lock"))
    if not os.path.isfile(lockfile):
        with open(lockfile, 'w') as lock:
            lock.writelines("file mutex\n")
    return lockfile


def export(config=None,
           base_dir=None,
           service_url=None,
           public=False,
           files_only=False,
           quiet=False,
           propagate_logs=True,
           require_authentication=True,
           allow_anonymous_download=False,
           allow_concurrent_download=False,
           max_payload_size_mb=None,
           timeout=None,
           dcctx_cid="export/unknown",
           request_ip="ip-unknown"):
    try:
        with lock_file(get_lockfile_path(), mode='w', exclusive=not allow_concurrent_download, timeout=5) as lf:
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

                    # parse credential params, if found in the request payload (unlikely)
                    token = catalog_config.get("token", None)
                    oauth2_token = catalog_config.get("oauth2_token", None)
                    username = catalog_config.get("username", "anonymous")
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
                    if not oauth2_token:
                        oauth2_token = get_bearer_token(web.ctx.env.get('HTTP_AUTHORIZATION'))
                    credentials = format_credential(token=token if token else web.cookies().get("webauthn"),
                                                    oauth2_token=oauth2_token,
                                                    username=username,
                                                    password=password)
                except (ValueError, HTTPError) as e:
                    if require_authentication:
                        raise Unauthorized(format_exception(e))
                finally:
                    if session:
                        session.close()
                        del session

                wallet = None
                identity = get_client_identity()
                if identity:
                    try:
                        wallet = get_client_wallet()
                    except (KeyError, AttributeError) as e:
                        raise BadRequest(format_exception(e))
                    if require_authentication and not (identity and wallet):
                        raise Unauthorized()

                user_id = username if not identity else identity.get('display_name', identity.get('id'))
                create_access_descriptor(base_dir,
                                         identity=None if not identity else identity.get('id'),
                                         public=public or not require_authentication)
                try:
                    sys_logger.info("Creating export at [%s] on behalf of %s at %s" % (base_dir, user_id, request_ip))
                    envars = {"request_ip": request_ip}
                    if service_url:
                        envars.update({GenericDownloader.SERVICE_URL_KEY: service_url})
                    downloader = GenericDownloader(server=server,
                                                   output_dir=base_dir,
                                                   envars=envars,
                                                   config=config,
                                                   credentials=credentials,
                                                   allow_anonymous=allow_anonymous_download,
                                                   max_payload_size_mb=max_payload_size_mb,
                                                   timeout=timeout,
                                                   dcctx_cid=dcctx_cid)
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

    except (LockException, AlreadyLocked) as e:
        raise Forbidden("Multiple concurrent exports per user are not supported. %s" % format_exception(e))
