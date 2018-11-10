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
import re
from deriva.core import urlquote, DerivaServer, ermrest_config as _ec
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

tag = _ec.AttrDict({
    'custom_tracks': 'tag:isrd.isi.edu,2018:custom-tracks',
})

HANDLER_CONFIG_FILE = os.path.join(DEFAULT_HANDLER_CONFIG_DIR, "track_config.json")

KEY_HOSTNAME = 'hostname'
KEY_URL_PATTERN = 'url_pattern'
KEY_TRACK_LINE_PATTERN = 'track_line_pattern'
KEY_TRACK_DESCRIPTION_HTML_PATTERN = 'track_description_html_pattern'
KEY_CANDIDATE_COLUMN_NAMES = 'candidate_column_names'
KEY_EXT_TO_TYPE = 'ext_to_type'

DEFAULT_CONFIG = {
    KEY_HOSTNAME: platform.node(),
    KEY_TRACK_DESCRIPTION_HTML_PATTERN: "<h2>Track Details</h2><p>For more information, please visit <a href='https://{hostname}/id/{catalog}/{RID}'>{catalog}/{RID}</a>.</p>",
    KEY_CANDIDATE_COLUMN_NAMES: {
        'name': ['name', 'filename', 'file_name', 'RID'],
        'description': ['description', 'caption', 'label'],
        'url': ['url', 'uri', 'path', 'file'],
        'type': ['type', 'file_type', 'filetype']
    },
    KEY_EXT_TO_TYPE: {
        'bam': 'bam',
        'bed': 'bed',
        'bb': 'bigBed',
        'wig': 'wiggle',
        'bw': 'bigWig'
    }
}

__default_url_pattern = '/entity/{schema}:{table}/{filter}'
__default_track_line_pattern = 'track type={type} name="{name}" description="{description}" htmlUrl=https://{hostname}/deriva/track/description/{catalog}/{schema}:{table}/RID={RID} bigDataUrl={url}\n'


def _get_table_definition(catalog, schema, table):
    """Get the table definition from the catalog schema resource.

    :param catalog: ermrest catalog object
    :param schema: schema name
    :param table: table name
    :return: table definition
    :raise requests.HTTPError: on failure of ERMrest requests
    """
    response = catalog.get('/schema/{schema}/table/{table}'.format(
        schema=urlquote(schema), table=urlquote(table)))
    return response.json()


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
    hostname = config[KEY_HOSTNAME]

    # Service params for use in string interpolation later
    params = {
        'hostname': hostname,
        'catalog': catalog_id,
        'schema': urlquote(schema),
        'table': urlquote(table),
        'filter': ';'.join(['RID=' + rid for rid in rids.split(',')]),
        'assembly': urlquote(assembly) if assembly else None
    }

    # Create catalog connection
    server = DerivaServer('https', hostname)
    catalog = server.connect_ermrest(catalog_id)

    # Get annotation for the target schema:table
    table_definition = _get_table_definition(catalog, schema, table)
    properties = config.copy()  # use config as defaults
    is_custom_track_table = tag.custom_tracks in table_definition['annotations']
    properties.update(table_definition['annotations'].get(tag.custom_tracks, {}))

    # Is inference needed?
    if is_custom_track_table or KEY_URL_PATTERN in properties or KEY_TRACK_LINE_PATTERN in properties:
        # The table was annotated or the deployment was configured, so no inference needed or attempted.
        logger.debug("Table '{}' was annotated or catalog was configured, no inference needed.".format(table))

        def row_iter(input_rows):
            """A simple row iterator that combines entity properties and service params."""
            for raw in input_rows:
                data = params.copy()
                data.update(raw)
                yield data
    else:
        # The table was not annotated nor was the deployment (sufficiently) configured, so attempt to infer properties.

        # First, look for column names or ways to map to columns for the data needed in the default track line
        col_names = {col['name'].lower(): col['name'] for col in table_definition['column_definitions']}
        logger.debug("Looking for suitable columns in {}".format(col_names))
        column_mapping = dict(RID='RID')  # RID is always RID
        cname_candidates = config[KEY_CANDIDATE_COLUMN_NAMES]
        for key in cname_candidates:
            for cname_candidate in cname_candidates[key]:
                if cname_candidate in col_names:
                    column_mapping[key] = col_names[cname_candidate]
                    break

        # Look for an asset annotation and overwrite any inferred mappings
        for col in table_definition['column_definitions']:
            if _ec.tag.asset in col['annotations']:
                column_mapping['url'] = col['name']
                logger.debug("Asset column '{}' found".format(col['name']))
                break

        # Finally, try to resolve any unsatisfied mappings, if possible
        if 'url' not in column_mapping:
            raise Exception("Unsatisfiable mapping. Could not find 'url' column in '{schema}:{table}".format(**params))
        if 'name' not in column_mapping:
            column_mapping['name'] = 'RID'
        if 'description' not in column_mapping:
            column_mapping['description'] = column_mapping['name']
        if 'type' not in column_mapping:
            logger.debug("No mapping for 'type' column inferred. Will attempt to infer from file extension.")
        logger.debug("Inferred column mappings {}".format(column_mapping))

        def row_iter(input_rows):
            """An iterator that maps the original row keys and alters data as needed"""
            ext_to_type = config[KEY_EXT_TO_TYPE]
            ext_regex = re.compile(r".*[.](?P<ext>{})([:][^/]*)?$".format('|'.join(ext_to_type.keys())))

            def infer_track_type_from_ext(values):
                """Does regex match to infer track type from file extension in set of values."""
                for value in values:
                    m = ext_regex.match(value)
                    if m:
                        ext = m.group('ext')
                        return ext_to_type[ext]
                return ''

            for raw in input_rows:
                data = params.copy()
                for key in column_mapping:
                    data[key] = raw[column_mapping[key]]
                # make sure that the inferred 'type' column really is a track type
                if 'type' not in data or data['type'] not in ext_to_type.values():
                    data['type'] = infer_track_type_from_ext([data['url'], data['name']])
                # make sure that 'url' is fully qualified
                if not data['url'].startswith('http'):
                    sep = '/' if not data['url'].startswith('/') else ''
                    data['url'] = 'https://{hostname}{sep}{path}'.format(hostname=hostname, sep=sep, path=data['url'])
                yield data

    # Get track metadata
    url = properties.get(KEY_URL_PATTERN, __default_url_pattern).format(**params)
    logger.debug("GET track metadata from '{}'".format(url))
    resp = catalog.get(url)
    rows = resp.json()

    # Make track lines from track metadata
    track_line_pattern = properties.get(KEY_TRACK_LINE_PATTERN, __default_track_line_pattern)
    track_lines = []
    for row in row_iter(rows):
        logger.debug('Track metadata {}'.format(row))
        track_lines.append(track_line_pattern.format(**row))

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
    hostname = config[KEY_HOSTNAME]

    # Create catalog connection
    server = DerivaServer('https', hostname)
    catalog = server.connect_ermrest(catalog_id)

    # Get annotation for the target schema:table
    table_definition = _get_table_definition(catalog, schema, table)
    properties = config.copy()  # use config as defaults
    properties.update(table_definition['annotations'].get(tag.custom_tracks, {}))

    params = {
        'hostname': hostname,
        'catalog': catalog_id,
        'schema': urlquote(schema),
        'table': urlquote(table),
        'RID': rid
    }

    return properties['track_description_html_pattern'].format(**params)
