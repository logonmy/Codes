from __future__ import with_statement
from fabric.api import *
from fabric.contrib.project import rsync_project
from fabric.contrib.console import confirm

# env.hosts = ['root@tshbao-task-01', 'root@tshbao-task-02', 'root@xiniudata-dev-01']
# env.hosts = ['root@xiniudata-dev-01']
env.hosts = ['root@xiniudata-nlp-01', 'root@xiniudata-dev-01']


def rsync():
    rsync_project(
            remote_dir="/data/task-201606/",
            local_dir="../data/spider2",
            exclude=(".*", "*.pyc", 'logs', '*.log', 'tmp', 'cach', 'model'),
            delete=('spider2/')
            )