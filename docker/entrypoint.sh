#!/bin/sh
set -eu
umask 0077
mkdir -p /data /data/keys /data/tmp /data/backups /run/php storage/framework/cache/data storage/framework/sessions storage/framework/views storage/logs bootstrap/cache
chown www-data:www-data /data /data/keys /data/tmp /data/backups /run/php
chown -R www-data:www-data storage bootstrap/cache
gosu www-data python3 docker/provision.py
if [ "${1:-serve}" = "worker" ]; then
    exec gosu www-data /opt/worker-venv/bin/python python/worker.py
fi
flock /data/migrations.lock gosu www-data php artisan migrate --force --no-interaction
if [ "${1:-serve}" = "serve" ]; then
    exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
fi
exec gosu www-data "$@"
