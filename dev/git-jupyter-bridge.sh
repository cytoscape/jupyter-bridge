#!/bin/bash

BRANCH=$1

if [[ -z $BRANCH ]]; then
        BRANCH='master'
fi

rm -rf jupyter-bridge
git clone -b $BRANCH https://github.com/cytoscape/jupyter-bridge
chmod +x jupyter-bridge/dev/*.sh

echo Remember to execute jupyter-bridge/dev/restart-uwsgi
