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
import itertools
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
KEY_URL_PATTERN = 'track_query_url_pattern'
KEY_TRACK_LINE_PATTERN = 'track_line_pattern'
KEY_TRACK_DESCRIPTION_HTML_PATTERN = 'track_description_html_pattern'
KEY_TRACK_COLUMN_NAMES = 'track_column_names'
KEY_EXT_TO_TYPE = 'track_file_ext_to_type'

DEFAULT_CONFIG = {
    KEY_HOSTNAME: platform.node(),
    KEY_TRACK_DESCRIPTION_HTML_PATTERN: "<h2>Track Details</h2><p>For more information, please visit <a href='https://{hostname}/id/{catalog}/{RID}'>{catalog}/{RID}</a>.</p>",
    KEY_TRACK_LINE_PATTERN: 'track type={Type} name="{Name}" description="{Description}" htmlUrl=https://{hostname}/deriva/track/description/{catalog}/{schema}:{table}/RID={Container_RID} bigDataUrl={URL}\n',
    KEY_TRACK_COLUMN_NAMES: {
        'Name': r"((file[ _-]?)?name)",
        'Description': r"(description|caption|title|label|comment)",
        'URL': r"(ur[il]|path|asset)",
        'Type': r"((track|file|data)[ _-]?)?type",
        'Genome_Assembly': r"(((reference[ -_]?)?genome|mapping|reference)?[ -_]?(assembly|genome))"
    },
    KEY_EXT_TO_TYPE: {
        'bam': 'bam',
        'bed': 'bed',
        'bb': 'bigBed',
        'wig': 'wiggle',
        'bw': 'bigWig'
    }
}


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


def _infer_track_query(table_definition, track_column_names, genome_assembly=None, url_template='{schema}:{table}/{filter}{attributes}', container_rid='RID'):
    """Infers a track query (url) from a table definition.

    :param table_definition: the introspected table definition
    :param track_column_names: track column names mapped to regular expressions
    :param genome_assembly: genome assembly to filter query on
    :param url_template: url template for forming query url
    :param container_rid: the attribute projection for the container's RID
    :return: track query url
    """
    # First, look for column names or ways to map to columns for the data needed in the default track line
    column_mapping = dict(RID='RID')  # RID is always RID
    for key in track_column_names:
        regex = re.compile(track_column_names[key], re.IGNORECASE)
        for col in table_definition['column_definitions']:
            if regex.match(col['name']):
                column_mapping[key] = col['name']
                break

    # Look for an asset annotation and overwrite any inferred attributes
    for col in table_definition['column_definitions']:
        if _ec.tag.asset in col.get('annotations', []):
            column_mapping['URL'] = col['name']
            logger.debug("'{cname}' has '{tag}' annotation".format(tag=_ec.tag.asset, cname=col['name']))
            break

    # Finally, try to resolve any unsatisfied attributes, if possible
    if 'Name' not in column_mapping:
        column_mapping['Name'] = 'RID'
    if 'Description' not in column_mapping:
        column_mapping['Description'] = column_mapping['Name']
    if 'Type' not in column_mapping:
        logger.debug("No mapping for 'Type' column inferred. Will attempt to infer from file extension.")
    logger.debug("Inferred attributes {}".format(column_mapping))

    # URL required for this to be a potential track table
    if 'URL' not in column_mapping:
        return None

    # Test if genome assembly is available for filter
    if genome_assembly and 'Genome_Assembly' not in column_mapping:
        logger.info("'Genome_Assembly' not found in '{schema}:{table}' but client requested to filter on it.".format(
            schema=table_definition['schema_name'], table=table_definition['table_name']
        ))
        return None

    url = url_template.format(
        schema=urlquote(table_definition['schema_name']),
        table=urlquote(table_definition['table_name']),
        filter='%s=%s/' % (urlquote(column_mapping['Genome_Assembly']), urlquote(genome_assembly)) if genome_assembly else '',
        attributes=','.join([
            '%s:=%s' % (urlquote(k), urlquote(v))
            for (k, v) in column_mapping.items()
        ] + ['Container_RID:=%s' % container_rid])
    )
    return url


def create_custom_tracks_content(config, catalog_id, schema, table, rids, genome_assembly=None):
    """Create CustomTracks content.

    :param config: configuration object
    :param catalog_id: catalog identifier
    :param schema: schema name
    :param table: table name
    :param rids: comma-separated list of RIDs
    :param genome_assembly: reference genome assembly (e.g., mm9, mm10, hg18, hg19,...)
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
        'Genome_Assembly': urlquote(genome_assembly) if genome_assembly else None
    }

    # Create catalog connection
    server = DerivaServer('https', hostname)
    catalog = server.connect_ermrest(catalog_id)

    # Get annotation for the target schema:table
    table_definition = _get_table_definition(catalog, schema, table)
    properties = config.copy()  # use config as defaults
    properties.update(table_definition['annotations'].get(tag.custom_tracks, {}))

    # Is inference needed?
    if tag.custom_tracks in table_definition['annotations'] or KEY_URL_PATTERN in properties:
        # The table was annotated or the deployment was configured, so no inference needed or attempted.
        logger.debug("Table '{}' was annotated or catalog was configured, no inference needed.".format(table))
        query_urls = [pattern.format(**params) for pattern in properties.get(KEY_URL_PATTERN, ['/entity/{schema}:{table}/{filter}'])]
    else:
        # Introspect table definition and infer track properties, if possible.
        logger.debug("Table '{}' requires inference")
        inferred_url = _infer_track_query(
            table_definition,
            config[KEY_TRACK_COLUMN_NAMES],
            genome_assembly=genome_assembly,
            url_template='/attribute/{schema}:{table}/{filter}/{inferred}'.format(inferred='{filter}{attributes}', **params))
        if inferred_url:
            query_urls = [inferred_url]
        else:
            # Deeper introspection of the model now to look at related tables
            model = catalog.getCatalogModel()
            container = model.schemas[schema].tables[table]
            query_urls = []
            for fkey in container.referenced_by:
                # See if we can infer a track query from the related table
                # TODO: go one more level deep if the fkey is from an association table
                inferred_url = _infer_track_query(model.schemas[fkey.sname].tables[fkey.tname].prejson(),
                                                  config[KEY_TRACK_COLUMN_NAMES],
                                                  genome_assembly=genome_assembly,
                                                  container_rid='CONTAINER:RID')
                if inferred_url:
                    query_urls.append('/attribute/CONTAINER:={schema}:{table}/{filter}/{inferred}'.format(inferred=inferred_url, **params))

            if not query_urls:
                # TODO define exception class
                raise Exception("Could not infer track table properties from '{schema}:{table}'".format(schema=schema, table=table))

    def row_iter(input_rows):
        """An iterator that attempts to fix input values to comply with genome browsers"""
        ext_to_type = config[KEY_EXT_TO_TYPE]
        ext_regex = re.compile(r".*[.](?P<ext>{})([:][^/]*)?$".format('|'.join(ext_to_type.keys())))

        def infer_track_type(*values):
            """Does regex match to infer track type from file extension in set of values."""
            for value in values:
                m = ext_regex.match(value)
                if m:
                    ext = m.group('ext')
                    return ext_to_type[ext]
            return None

        for raw in input_rows:
            data = params.copy()  # copy in the service params first so that track line interpolation can use them
            data.update(raw)  # update (and possibly overwrite) with values from the catalog
            # make sure that the inferred 'Type' column really is a track type
            if 'Type' not in data or data['Type'] not in ext_to_type.values():
                track_type = infer_track_type(data['URL'], data['Name'])
                if track_type:
                    data['Type'] = track_type
                else:
                    # Could not infer or validate a correct track type; skip this track
                    continue
            # make sure that 'url' is fully qualified (TODO: may need to remove the `:version` suffix. TBD)
            if not data['URL'].startswith('http'):
                sep = '/' if not data['URL'].startswith('/') else ''
                data['URL'] = 'https://{hostname}{sep}{path}'.format(hostname=hostname, sep=sep, path=data['URL'])
            yield data

    # Get track metadata
    logger.debug("Getting tracks for query urls '{}'".format(query_urls))
    rows = row_iter(itertools.chain(*[catalog.get(url).json() for url in query_urls]))

    # Make track lines from track metadata
    track_line_pattern = properties[KEY_TRACK_LINE_PATTERN]
    track_lines = [track_line_pattern.format(**row) for row in rows]
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

    return properties[KEY_TRACK_DESCRIPTION_HTML_PATTERN].format(**params)
