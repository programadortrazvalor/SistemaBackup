FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY vite.config.js ./
COPY resources ./resources
RUN npm run build

FROM composer:2 AS dependencies
WORKDIR /app
COPY composer.json composer.lock ./
RUN composer install --no-dev --no-interaction --prefer-dist --no-scripts --no-autoloader
COPY app ./app
RUN composer dump-autoload --no-dev --optimize --no-scripts

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive TZ=America/Cuiaba BACKUP_DATA_PATH=/data BACKUP_APP_PATH=/var/www/html
RUN apt-get update && apt-get install -y --no-install-recommends \
    php8.3-cli php8.3-fpm php8.3-pgsql php8.3-mbstring php8.3-xml php8.3-curl php8.3-zip \
    mysql-client postgresql-client sqlite3 gzip python3 python3-venv nginx supervisor gosu curl ca-certificates tzdata util-linux \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /var/www/html
COPY python/requirements.txt /tmp/worker-requirements.txt
RUN python3 -m venv /opt/worker-venv && /opt/worker-venv/bin/pip install --no-cache-dir -r /tmp/worker-requirements.txt
COPY . .
COPY --from=dependencies /app/vendor ./vendor
COPY --from=frontend /build/public/build ./public/build
COPY docker/nginx.conf /etc/nginx/sites-available/default
COPY docker/supervisord.conf /etc/supervisor/conf.d/backup.conf
COPY docker/php.ini /etc/php/8.3/fpm/conf.d/99-backup.ini
COPY docker/php.ini /etc/php/8.3/cli/conf.d/99-backup.ini
COPY docker/fpm-pool.conf /etc/php/8.3/fpm/pool.d/zz-backup.conf
COPY docker/entrypoint.sh /usr/local/bin/backup-entrypoint
RUN chmod +x /usr/local/bin/backup-entrypoint && mkdir -p /run/php /certs /sqlite \
    && chown -R www-data:www-data storage bootstrap/cache /run/php
EXPOSE 80
ENTRYPOINT ["/usr/local/bin/backup-entrypoint"]
CMD ["serve"]
