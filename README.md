# deriva-web
REST Web Service Interface for DERIVA components.

The `deriva` webservice provides a REST interface facade for various Deriva software components. The following endpoints are exposed:
1. The `export` endpoint supports export of data from ERMRest/Hatrac to either individual files or as filesets contained within
 [BagIt](https://datatracker.ietf.org/doc/draft-kunze-bagit/) serialized archive files.


### Prerequisites
1. Python 2.7 or higher
2. ERMrest installed.
3. Webauthn installed.

### Installation
1. Clone source from GitHub:
    * `git clone https://github.com/informatics-isi-edu/deriva-web.git`


2. From the source distribution base directory, run:
    * `make deploy`

### Configuration

See the [Configuration guide](./doc/config.md) for further details.

### Usage

1. Export:
    * See the `export` endpoint [API guide](./doc/export/api.md) for further details.

### Integration with Chaise

1. Export:
    * See the `export` endpoint [Integration guide](./doc/export/integration.md) for further details.
