#!/bin/sh

set -eu

umask 077

data_dir=${NEXORA_DATA_DIR:-/data}

if [ ! -d "$data_dir" ] || [ ! -w "$data_dir" ]; then
    echo "NEXORA_DATA_DIR must exist and be writable: $data_dir" >&2
    exit 1
fi

for directory in \
    database credentials hostkeys logs tasks task-output operations audit \
    console runtime backups progress cache recovery
do
    install -d -m 0700 "$data_dir/$directory"
done

exec "$@"

