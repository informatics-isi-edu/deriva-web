
# this ugly hack necessitated by Ubuntu... grrr...
SYSPREFIX=$(shell python3 -c 'import site;print(site.getsitepackages()[0])' | sed -e 's|/[^/]\+/[^/]\+/[^/]\+$$||')
# try to find the architecture-neutral lib dir by looking for one of our expected prereqs... double grrr...
PYLIBDIR=$(shell python3 -c 'import site;import os.path;print([d for d in site.getsitepackages() if os.path.exists(d+"/web")][0])')

CONFDIR=/etc
SHAREDIR=$(SYSPREFIX)/share/deriva

ifeq ($(wildcard /etc/httpd/conf.d),/etc/httpd/conf.d)
		HTTPSVC=httpd
else
		HTTPSVC=apache2
endif

HTTPDCONFDIR=/etc/$(HTTPSVC)/conf.d
WSGISOCKETPREFIX=/var/run/$(HTTPSVC)/wsgi
DAEMONUSER=deriva
DERIVAWEBDATADIR=/var/www/deriva

# turn off annoying built-ins
.SUFFIXES:

INSTALL_SCRIPT=./install-script

UNINSTALL_DIRS=$(SHAREDIR)

UNINSTALL=$(UNINSTALL_DIRS)
#       $(BINDIR)/deriva-db-init

# make this the default target
install: conf/wsgi_deriva.conf conf/deriva_config.json bin/deriva-web-export-prune
		pip3 install --no-deps 'bagit==1.7.0'
		pip3 install --no-deps 'bdbag>=1.5.6'
		pip3 install --no-deps .

testvars:
		@echo DAEMONUSER=$(DAEMONUSER)
		@echo CONFDIR=$(CONFDIR)
		@echo SYSPREFIX=$(SYSPREFIX)
		@echo SHAREDIR=$(SHAREDIR)
		@echo HTTPDCONFDIR=$(HTTPDCONFDIR)
		@echo DERIVAWEBDATADIR=${DERIVAWEBDATADIR}
		@echo WSGISOCKETPREFIX=$(WSGISOCKETPREFIX)
		@echo PYLIBDIR=$(PYLIBDIR)

deploy: install
		env SHAREDIR=$(SHAREDIR) HTTPDCONFDIR=$(HTTPDCONFDIR) DERIVAWEBDATADIR=${DERIVAWEBDATADIR} SYSPREFIX=$(SYSPREFIX) deriva-web-deploy

redeploy: uninstall deploy

conf/wsgi_deriva.conf: conf/wsgi_deriva.conf.in
		./install-script -M sed -R @PYLIBDIR@=$(PYLIBDIR) @WSGISOCKETPREFIX@=$(WSGISOCKETPREFIX) @DAEMONUSER@=$(DAEMONUSER) -o root -g root -m a+r -p -D $< $@

conf/deriva_config.json: conf/deriva_config.json.in
		./install-script -M sed -R  @DERIVAWEBDATADIR@=${DERIVAWEBDATADIR} -o root -g root -m a+r -p -D $< $@

bin/deriva-web-export-prune: conf/deriva-web-export-prune.in
		./install-script -M sed -R  @DERIVAWEBDATADIR@=${DERIVAWEBDATADIR} -o root -g root -m a+r -p -D $< $@

uninstall:
		-pip3 uninstall -y deriva.web
		rm -f /home/${DAEMONUSER}/deriva_config.json
		rm -f ${HTTPDCONFDIR}/wsgi_deriva.conf
		rm -f /etc/cron.daily/deriva-web-export-prune
#       -rmdir --ignore-fail-on-non-empty -p $(UNINSTALL_DIRS)

preinstall_centos:
		yum -y install python3 python3-pip python3-psycopg2 python3-dateutil pytz python3-tzlocal

preinstall_ubuntu:
		apt-get -y install python python3-pip python3-psycopg2 python3-dateutil python3-tz

