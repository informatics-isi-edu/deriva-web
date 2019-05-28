# `deriva-web` Configuration Guide
The service uses two files for configuration: `deriva_config.json` for service specific configuration and `wsgi_deriva.conf` to configure WSGI module support in Apache HTTPD.

### deriva_config.json
The installation and deployment process creates a `deriva` user on the local system, including a home directory for this user.  The service-specific configuration file `deriva_config.json` is located in this directory.

Below is a sample of the default configuration file:

```json
{
    "storage_path": "/var/www/deriva/data",
    "authentication":"webauthn",
    "404_html": "<html><body><h1>Resource Not Found</h1><p>The requested resource could not be found at this location.</p><p>Additional information:</p><p><pre>%(message)s</pre></p></body></html>",
    "403_html": "<html><body><h1>Access Forbidden</h1><p>%(message)s</p></body></html>",
    "401_html": "<html><body><h1>Authentication Required</h1><p>%(message)s</p></body></html>",
    "400_html": "<html><body><h1>Bad Request</h1><p>One or more request parameters are incorrect.</p><p>Additional information:</p><p><pre>%(message)s</pre></p></body></html>"
}
```

* The `storage_path` variable is an absolute path to the base directory where the service stores file data.
* The `authentication` variable is an optional string value representing the authentication mechanism to use.  Valid values are `"webauthn"` or `None`, or the key can be ommitted, which is equivalent to specifiying `None`.
* The various `"*_html"` variables are for specifying customized HTML error template responses for API functions.

### wsgi_deriva.conf
The `wsgi_deriva.conf` file is installed to `/etc/httpd/conf.d`. Below is an example of the default:
```
# this file must be loaded (alphabetically) after wsgi.conf
AllowEncodedSlashes On

WSGIPythonOptimize 1
WSGIDaemonProcess deriva processes=8 threads=4 user=deriva maximum-requests=2000
WSGIScriptAlias /deriva /usr/lib/python2.7/site-packages/deriva/deriva.wsgi
WSGIPassAuthorization On

WSGISocketPrefix /var/run/httpd/wsgi

<Location "/deriva" >
   AuthType webauthn
   Require webauthn-optional

   WSGIProcessGroup deriva

   SetEnv dontlog
</Location>
```
