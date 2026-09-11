#!/bin/bash
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y build-essential curl git libpq-dev nginx python3-dev python3-venv

if ! id routine-market >/dev/null 2>&1; then
    useradd --system --home /srv/routine-market --shell /usr/sbin/nologin routine-market
fi

if [ ! -d /srv/routine-market/.git ]; then
    git clone https://github.com/Aa26178787/routine_market.git /srv/routine-market
fi

python3 -m venv /srv/routine-market/.venv
/srv/routine-market/.venv/bin/pip install --upgrade pip
/srv/routine-market/.venv/bin/pip install -r /srv/routine-market/requirements.txt

chown -R routine-market:www-data /srv/routine-market
install -o root -g root -m 0644 /srv/routine-market/deploy/routine-market.service /etc/systemd/system/routine-market.service
install -o root -g root -m 0644 /srv/routine-market/deploy/nginx-routine-market.conf /etc/nginx/sites-available/routine-market
ln -sfn /etc/nginx/sites-available/routine-market /etc/nginx/sites-enabled/routine-market
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl daemon-reload
systemctl enable routine-market nginx
systemctl restart nginx
