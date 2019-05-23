# deriva/export REST API reference
The `deriva/export` service endpoint provides export functionality from an ERMrest catalog via a REST API.
The service is generally configured to be co-located on the same server with the ERMrest catalog that it is providing data services for.

**Exporting individual files**
----

This API endpoint is used to perform one or more queries to an ERMrest catalog and create corresponding individual 
result files which can then be retrieved via `GET`.  URLs for result files are returned in the response body as `Content-Type:text/uri-list`.

----

#### Export file(s)
Executes one more ERMrest queries and writes the results to individual files.
 
###### **URL**

/deriva/export/file

###### **Method:**

`POST`

###### **URL Params**
	
None

###### **Data Params**

The input data is composed of a JSON object with the following form:

##### root (object)

| Variable | Type | Inclusion| Description |
| --- | --- | --- | --- |
| `catalog` | `catalog` | required | A `catalog` object. See below.

##### `catalog` (object)

| Variable | Type | Inclusion| Description |
| --- | --- | --- | --- |
| `host`| string | required | The hostname (and port) of the ERMrest service to query.
| `catalog_id` | string | optional | The catalog identifier, e.g. `1`.
| `username` | string | optional | If `username` is not specified, authentication is assumed to come from the `webauthn` authentication context stored in the caller's cookie.
| `password` | string | optional | The `password` field is only used when `username` is specifed.
| `queries` | array[`query`] | required | An array of `query` objects. See below.

##### `query` (object)

| Parent Object | Variable | Type | Inclusion| Description |Interpolatable |
| --- | --- | --- | --- | --- | --- |
|*query*|*processor*|string|required|This is a string value used to select from one of the built-in query output processor formats. Valid values are `env`, `csv`, `json`, `json-stream`, `download`, or `fetch`.|No
|*query*|*processor_type*|string|optional|A fully qualified Python class name declaring an external processor class instance to use. If this parameter is present, it OVERRIDES the default value mapped to the specified `processor`. This class MUST be derived from the base class `deriva.transfer.download.processors.BaseDownloadProcessor`. For example, `"processor_type": "deriva.transfer.download.processors.CSVDownloadProcessor"`.|No
|*query*|*processor_params*|object|required|This is an extensible JSON Object that contains processor implementation-specific parameters.|No
|*processor_params*|*query_path*|string|required|This is string representing the actual `ERMRest` query path to be used in the HTTP(S) GET request. It SHOULD already be percent-encoded per [RFC 3986](https://tools.ietf.org/html/rfc3986#section-2.1) if it contains any characters outside of the unreserved set.|Yes
|*processor_params*|*output_path*|string|required|This is a POSIX-compliant path fragment indicating the target location of the retrieved data relative to the specified base download directory.|Yes


###### **Success Response:**
**Code:** 200 

**Content:**
```
http://localhost:8080/deriva/export/file/9ad15e5b-9c2c-4faf-8829-05fa8252c8bc/genotypes.csv
http://localhost:8080/deriva/export/file/9ad15e5b-9c2c-4faf-8829-05fa8252c8bc/phenotypes.csv
```
 
###### **Error Responses:**

* **404:**  NOT FOUND 
* **401:**  UNAUTHORIZED 
* **400:**  BAD REQUEST 
* **500:**  INTERNAL SERVER ERROR 

###### **Sample Call:**

```javascript
var exportParameters =
{
    "catalog":
    {
        "host": "http://localhost:8080",
        "catalog_id": "1",
        "username": "devuser",
        "password": "devpass",
        "query_processors": [
            {
                "processor": "csv",
                "processor_params": {
                    "query_path": "/entity/A:=dev:subject/A1:=snp_v/snp_id=rs6265",
                    "output_path": "genotypes",
                }
            },
            {
                "processor": "csv",
                "processor_params": {
                    "query_path": "/entity/A:=dev:subject/A1:=snp_v/snp_id=rs6265/$A/B:=dev:subject_phenotypes_v",
                    "output_path": "phenotypes",
                }
            }
        ]
    }
};

$.ajax({
    url: "/deriva/export/file",
    dataType: "json",
    type : "POST",
    data: exportParameters,
    success : function(r) {
      console.log(r);
    }
});
```
----

#### Retrieve exported file(s)
Retrieves a file previously created by a `POST`.

###### **URL**

/deriva/export/file/\<id\>/\<filename\>

###### **Method:**

`GET`
  
######  **URL Params**
	
**Required:**

`id=[string]`

**Optional:**

`filename=[string]` - This argument is required when the `uri-list` returned from `POST` contains more than one entry. 
If it is not specified and there is more than one file result, a `400 Bad Request` is returned.

###### **Data Params**

None

###### **Success Response:**

**Code:** 200 

**Content:** The file content.
 
###### **Error Responses:**

* **404:**  NOT FOUND 
* **403:**  FORBIDDEN 
* **401:**  UNAUTHORIZED 
* **400:**  BAD REQUEST 
* **500:**  INTERNAL SERVER ERROR 

###### **Sample Call:**

```javascript	
$.ajax({
    url: "/deriva/export/file/9ad15e5b-9c2c-4faf-8829-05fa8252c8bc/genotypes.csv",
    type : "GET",
    success : function(r) {
      console.log(r);
    }
});
```
----	

#### Retrieve log file for exported file(s)
Retrieves the log file generated by an invocation of `POST`.

###### **URL**

/deriva/export/file/\<id\>/log

###### **Method:**

`GET`
  
###### **URL Params**
	
**Required:**

`id=[string]`

###### **Data Params**

None

###### **Success Response:**

**Code:** 200

**Content:** The file content.
 
###### **Error Responses:**

* **404:**  NOT FOUND
* **403:**  FORBIDDEN
* **401:**  UNAUTHORIZED
* **400:**  BAD REQUEST
* **500:**  INTERNAL SERVER ERROR

###### **Sample Call:**

```javascript
$.ajax({
    url: "/deriva/export/file/9ad15e5b-9c2c-4faf-8829-05fa8252c8bc/log",
    type : "GET",
    success : function(r) {
      console.log(r);
    }
});
```
	
**Exporting Bags**
----

This API endpoint is used to perform one or more queries to an ERMrest catalog and create a 
[BDBag](https://github.com/fair-research/bdbag) archive file which can then be retrieved via `GET`.  The URL for the result bag is returned in the response body as `Content-Type:text/uri-list`.


#### Export bag
Executes one more ERMrest queries and writes the results to a [BDBag](https://github.com/fair-research/bdbag).
 
###### **URL**

/deriva/export/bdbag

###### **Method:**

`POST`
  
###### **URL Params**
	
None

###### **Data Params**

The input data is composed of a JSON object with the following form:

##### root (object)

| Variable | Type | Inclusion| Description |
| --- | --- | --- | --- |
| `bag` | `bag` | required | A `bag` object. See below.
| `catalog` | `catalog` | required | A `catalog` object. See below.

##### `bag` (object)

| Variable | Type | Inclusion| Description |
| --- | --- | --- | --- |
| `bag_name`| string, enum [`"zip"`,`"tgz"`,`"bz2"`,`"tar"`] | required | The base file name of the bag. An appropriate extension will be added to the base depending on the archive type selected.
| `bag_archiver` | string | required | The archive format used to serialize the result bag.
| `bag_metadata` | object | optional | A simple 'dictionary' object consisting of key-value pairs. The only supported primitive type for value pairs is `string`. The metdata object will be written directly to the bag's `bag-info.txt` file.

##### `catalog` (object)

| Variable | Type | Inclusion| Description |
| --- | --- | --- | --- |
| `host`| string | required | The hostname (and port) of the ERMrest service to query.
| `catalog_id` | string | optional | The catalog identifier, e.g. `1`.
| `username` | string | optional | If `username` is not specified, authentication is assumed to come from the `webauthn` authentication context stored in the caller's cookie.
| `password` | string | optional | The `password` field is only used when `username` is specifed.
| `queries` | array[`query`] | required | An array of `query` objects. See below.

##### `query` (object)

| Parent Object | Variable | Type | Inclusion| Description |Interpolatable
| --- | --- | --- | --- | --- | --- |
|*query*|*processor*|string|required|This is a string value used to select from one of the built-in query output processor formats. Valid values are `env`, `csv`, `json`, `json-stream`, `download`, or `fetch`.|No
|*query*|*processor_type*|string|optional|A fully qualified Python class name declaring an external processor class instance to use. If this parameter is present, it OVERRIDES the default value mapped to the specified `processor`. This class MUST be derived from the base class `deriva.transfer.download.processors.BaseDownloadProcessor`. For example, `"processor_type": "deriva.transfer.download.processors.CSVDownloadProcessor"`.|No
|*query*|*processor_params*|object|required|This is an extensible JSON Object that contains processor implementation-specific parameters.|No
|*processor_params*|*query_path*|string|required|This is string representing the actual `ERMRest` query path to be used in the HTTP(S) GET request. It SHOULD already be percent-encoded per [RFC 3986](https://tools.ietf.org/html/rfc3986#section-2.1) if it contains any characters outside of the unreserved set.|Yes
|*processor_params*|*output_path*|string|required|This is a POSIX-compliant path fragment indicating the target location of the retrieved data relative to the specified base download directory.|Yes


###### **Success Response:**

**Code:** 200

**Content:**
```
http://localhost:8080/deriva/export/file/9ad15e5b-9c2c-4faf-8829-05fa8252c8bc/sample-bag.zip
```
 
###### **Error Responses:**

* **404:**  NOT FOUND
* **401:**  UNAUTHORIZED
* **400:**  BAD REQUEST
* **500:**  INTERNAL SERVER ERROR

###### **Sample Call:**

```javascript
var exportParameters =
{
    "bag":
    {
      "bag_name": "sample-bag",
      "bag_archiver":"zip",
      "bag_metadata":
      {
        "Source-Organization": "USC Information Sciences Institute, Informatics Systems Research Division",
        "Contact-Name": "Mike D'Arcy",
        "External-Description": "A bag containing a sample PheWas cohort for downstream analysis.",
        "Internal-Sender-Identifier": "USC-ISI-IRSD"
      }
    },
    "catalog":
    {
      "host": "https://localhost:8080",
      "path": "/ermrest/catalog/1",
      "username": "",
      "password": "",
      "queries":
      [
        {
          "processor": "csv",
          "query_path": "/entity/A:=pnc:subject/A1:=snp_v/snp_id=rs6265/$A/B:=pnc:metrics_v",
          "output_path": "metrics"
        },
        {
          "processor": "csv",
          "processor_params": {
            "query_path": "/entity/A:=pnc:subject/A1:=snp_v/snp_id=rs6265",
            "output_path": "genotypes"
          }
        },
        {
          "processor": "csv",
          "processor_params": {
            "query_path": "/entity/A:=pnc:subject/A1:=snp_v/snp_id=rs6265/$A/B:=pnc:subject_phenotypes_v",
            "output_path": "phenotypes"
          }
        },
        {
          "processor": "fetch",
          "processor_params": {
            "query_path": "/attribute/A:=pnc:subject/A1:=snp_v/snp_id=rs6265/$A/B:=pnc:image_files/filename::ciregexp::0mm.mgh/url:=B:uri,length:=B:bytes,filename:=B:filepath,sha256:=B:sha256sum",
            "output_path": "images"
          }
        }
      ]
    }
};

$.ajax({
    url: "/deriva/export/file",
    dataType: "json",
    type : "POST",
    data: exportParameters,
    success : function(r) {
      console.log(r);
    }
});
```
----

#### Retrieve an exported bag
Retrieves a bag previously created by a `POST`.

###### **URL**

/deriva/export/bdbag/\<id\>

###### **Method:**

`GET`
  
###### **URL Params**
	
**Required:**

`id=[string]`

###### **Data Params**

None

###### **Success Response:**

**Code:** 200

**Content:** The file content.
 
###### **Error Responses:**

* **404:**  NOT FOUND
* **403:**  FORBIDDEN
* **401:**  UNAUTHORIZED
* **400:**  BAD REQUEST
* **500:**  INTERNAL SERVER ERROR

###### **Sample Call:**

```javascript
$.ajax({
    url: "/deriva/export/file/9ad15e5b-9c2c-4faf-8829-05fa8252c8bc",
    type : "GET",
    success : function(r) {
      console.log(r);
    }
});
```
----	

#### Retrieve log file for exported bag
Retrieves the log file generated by an invocation of `POST`.

###### **URL**

/deriva/export/bdbag/\<id\>/log

###### **Method:**

`GET`
  
###### **URL Params**
	
**Required:**

`id=[string]`

###### **Data Params**

None

###### **Success Response:**

**Code:** 200

**Content:** The file content.
 
###### **Error Responses:**

  * **404:**  NOT FOUND
  * **403:**  FORBIDDEN
  * **401:**  UNAUTHORIZED
  * **400:**  BAD REQUEST
  * **500:**  INTERNAL SERVER ERROR

###### **Sample Call:**

```javascript
$.ajax({
    url: "/deriva/export/file/9ad15e5b-9c2c-4faf-8829-05fa8252c8bc/log",
    type : "GET",
    success : function(r) {
      console.log(r);
    }
});
```
