#!/bin/bash 

if [ $# -gt 0 ]; then
    root=$1
else
    root=$(pwd)
fi

python tornado_file_server/server.py --root $root --port 8080
