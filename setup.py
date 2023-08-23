#
# Copyright 2016-2023 University of Southern California
# Distributed under the Apache License, Version 2.0. See LICENSE for more info.
#

""" Installation script for the deriva web service.
"""
import os
from glob import glob
from setuptools import setup, find_packages


def get_data_files():
    target_dir = 'share/deriva'
    data_files = [
        (target_dir, [
            "conf/wsgi_deriva.conf",
        ]),
        (target_dir, [
            "conf/deriva_config.json",
        ])
    ]
    for root, dirs, files in os.walk("conf/conf.d"):
        files = [os.path.join(root, i) for i in files]
        if files:
            data_files.append((os.path.join(target_dir, root[len('conf/'):]), files))

    return data_files


setup(
    name='deriva.web',
    description='REST Web Service Interface for DERIVA components',
    url='https://github.com/informatics-isi-edu/deriva-web',
    maintainer='USC Information Sciences Institute ISR Division',
    maintainer_email='isrd-support@isi.edu',
    version="0.9.11",
    zip_safe=False,
    packages=find_packages(),
    scripts=["bin/deriva-web-deploy", "bin/deriva-web-export-prune"],
    package_data={'deriva.web': ["*.wsgi"]},
    data_files=get_data_files(),
    test_suite="tests",
    requires=[
        'requests',
        'certifi',
        "flask",
        "psycopg2",
        "webauthn2",
        "deriva",
        "bdbag"],
    license='Apache 2.0',
    classifiers=[
        'Intended Audience :: Science/Research',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        "Operating System :: POSIX",
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10'
        "Topic :: Internet :: WWW/HTTP"
    ]
)

