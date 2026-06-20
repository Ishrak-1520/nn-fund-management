#!/bin/bash
set -e

# This script injects Render's database environment variables into odoo.conf at runtime.
# Render provides HOST, PORT, USER, PASSWORD, DB_NAME via environment variables
# linked from the managed PostgreSQL service.

CONFIG_FILE="/etc/odoo/odoo.conf"

# Create a temporary config with injected values
cat > /tmp/odoo.conf << EOF
[options]
; Database settings (injected from Render environment)
admin_passwd = ${ADMIN_PASSWORD:-admin}
db_host = ${HOST:-localhost}
db_port = ${PORT:-5432}
db_user = ${USER:-odoo}
db_password = ${PASSWORD:-odoo}
db_name = ${DB_NAME:-False}
list_db = False
db_sslmode = require

; Addons path
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons

; Server settings
http_port = 8069
proxy_mode = True
without_demo = False

; Logging (stdout for Render)
log_level = info
logfile = 

; Performance (free tier has limited RAM ~512MB)
workers = 0
max_cron_threads = 1
limit_memory_hard = 536870912
limit_memory_soft = 419430400
limit_time_cpu = 600
limit_time_real = 1200
EOF

# Start Odoo with the generated config
exec odoo -c /tmp/odoo.conf "$@"
