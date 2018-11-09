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
import logging
import platform
import requests
from deriva.core import urlquote, DerivaServer
from deriva.core.ermrest_config import AttrDict as _AttrDict
from ..core import DEFAULT_HANDLER_CONFIG_DIR

# TODO: this is either not needed anymore or if it is should be pushed up a level
# import requests
# from requests.adapters import HTTPAdapter
# from requests.packages.urllib3.util.retry import Retry
# _session = requests.session()
# _retries = Retry(
#     connect=5,
#     read=5,
#     backoff_factor=1.0,
#     status_forcelist=[500, 502, 503, 504]
# )
# _session.mount('http://', HTTPAdapter(max_retries=_retries))
# _session.mount('https://', HTTPAdapter(max_retries=_retries))

logger = logging.getLogger("deriva.web.track")

tag = _AttrDict({
    'custom_tracks': 'tag:isrd.isi.edu,2018:custom-tracks',
})

HANDLER_CONFIG_FILE = os.path.join(DEFAULT_HANDLER_CONFIG_DIR, "track_config.json")

DEFAULT_CONFIG = {
    'hostname': platform.node(),
    'url_pattern': '/attribute/T:={schema}:{table}/{rid_filter}/assembly={assembly}/RID,description_RID:=RID,name,description,path,type?limit=1000',
    'track_line_pattern': 'track type={type} name="{name}" description="{description}" htmlUrl=https://{hostname}/deriva/track/description/{catalog}/{schema}:{table}/RID={description_RID} bigDataUrl=https://{hostname}{path}\n',
    'track_description_html_pattern': "<h2>Track Details</h2><p>For more information, please visit <a href='https://{hostname}/id/{catalog}/{RID}'>{catalog}/{RID}</a>.</p>"
}


def get_custom_tracks_annotation(catalog, schema, table):
    """Attempts to get the 'custom-tracks' annotation for the given schema:table

    :param catalog: ermrest catalog object
    :param schema: schema name
    :param table: table name
    :return: annotation object or {} if not found in the schema
    :raise requests.HTTPError: on failure of ERMrest requests
    """
    try:
        annotation = catalog.get('/schema/{schema}/table/{table}/annotation/{tag}'.format(
            schema=urlquote(schema), table=urlquote(table), tag=urlquote(tag.custom_tracks)))
    except requests.HTTPError as e:
        if e.response.status_code in [404, 409]:
            annotation = {}
        else:
            raise e
    return annotation


def create_custom_tracks_content(config, catalog_id, schema, table, rids, assembly=None):
    """Create CustomTracks content.

    :param config: configuration object
    :param catalog_id: catalog identifier
    :param schema: schema name
    :param table: table name
    :param rids: comma-separated list of RIDs
    :param assembly: mapping assembly
    :return: custom tracks text content
    :raise requests.HTTPError: on failure of ERMrest requests
    """
    hostname = config['hostname']

    # Create catalog connection
    server = DerivaServer('https', hostname)
    catalog = server.connect_ermrest(catalog_id)

    # Get annotation for the target schema:table
    annotation = config.copy()  # use config as defaults
    annotation.update(get_custom_tracks_annotation(catalog, schema, table))

    params = {
        'hostname': hostname,
        'catalog': catalog_id,
        'schema': urlquote(schema),
        'table': urlquote(table),
        'rid_filter': ';'.join(['RID=' + rid for rid in rids.split(',')]),
        'assembly': urlquote(assembly) if assembly else None
    }

    url = annotation['url_pattern'].format(**params)
    resp = catalog.get(url)
    rows = resp.json()

    track_lines = []
    for row in rows:
        data = params.copy()
        data.update(row)
        track_lines.append(annotation['track_line_pattern'].format(**data))

    return ''.join(track_lines)


def create_track_description_content(config, catalog_id, schema, table, rid):
    """Create track description.

    :param config: configuration object
    :param catalog_id: catalog identifier
    :param schema: schema name
    :param table: table name
    :param rid: RID
    :return: track description as HTML fragment text
    :raise requests.HTTPError: on failure of ERMrest requests
    """
    hostname = config['hostname']

    # Create catalog connection
    server = DerivaServer('https', hostname)
    catalog = server.connect_ermrest(catalog_id)

    # Get annotation for the target schema:table
    annotation = config.copy()  # use config as defaults
    annotation.update(get_custom_tracks_annotation(catalog, schema, table))

    params = {
        'hostname': hostname,
        'catalog': catalog_id,
        'schema': urlquote(schema),
        'table': urlquote(table),
        'RID': rid
    }

    return annotation['track_description_html_pattern'].format(**params)
