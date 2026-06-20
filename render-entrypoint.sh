#!/bin/bash
set -e

# In Odoo, db_host must be a hostname, not a connection URL.
# This script automatically parses full postgresql:// connection URLs if provided
# in either DATABASE_URL, INTERNAL_DATABASE_URL, or HOST.

DB_CONN_URL=""

if [[ "$DATABASE_URL" =~ ^postgres(ql)?:// ]]; then
    DB_CONN_URL="$DATABASE_URL"
elif [[ "$INTERNAL_DATABASE_URL" =~ ^postgres(ql)?:// ]]; then
    DB_CONN_URL="$INTERNAL_DATABASE_URL"
elif [[ "$HOST" =~ ^postgres(ql)?:// ]]; then
    DB_CONN_URL="$HOST"
fi

if [ -n "$DB_CONN_URL" ]; then
    echo "Parsing database connection URL..."
    # Remove protocol prefix
    temp="${DB_CONN_URL#*://}"
    
    # Extract credentials and host/db
    if [[ "$temp" == *"@"* ]]; then
        creds="${temp%%@*}"
        host_db="${temp#*@}"
        
        # Parse user and password
        if [[ "$creds" == *":"* ]]; then
            USER="${creds%%:*}"
            PASSWORD="${creds#*:}"
        else
            USER="$creds"
        fi
    else
        host_db="$temp"
    fi
    
    # Parse host, port and database name (format: host[:port]/database)
    db_part="${host_db#*/}"
    host_port="${host_db%%/*}"
    
    if [[ "$host_port" == *":"* ]]; then
        HOST="${host_port%%:*}"
        PORT="${host_port#*:}"
    else
        HOST="$host_port"
        PORT="5432"
    fi
    
    # Strip any trailing query params if present in database name
    DB_NAME="${db_part%%\?*}"
    
    echo "Successfully parsed connection URL:"
    echo "  Host: $HOST"
    echo "  Port: $PORT"
    echo "  User: $USER"
    echo "  Database: $DB_NAME"
else
    # Fallback to standard environment variables
    HOST="${HOST:-localhost}"
    PORT="${PORT:-5432}"
    USER="${USER:-odoo}"
    PASSWORD="${PASSWORD:-odoo}"
    DB_NAME="${DB_NAME:-False}"
fi

CONFIG_FILE="/etc/odoo/odoo.conf"

# Create a temporary config with injected values
cat > /tmp/odoo.conf << EOF
[options]
; Database settings
admin_passwd = ${ADMIN_PASSWORD:-admin}
db_host = ${HOST}
db_port = ${PORT}
db_user = ${USER}
db_password = ${PASSWORD}
db_name = ${DB_NAME}
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
