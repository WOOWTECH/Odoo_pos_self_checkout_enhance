#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
#
# HA add-on entrypoint. Reads /data/options.json via bashio and execs the
# Flask proxy with the configured API key and port.

set -euo pipefail

API_KEY=$(bashio::config 'api_key')
PORT=$(bashio::config 'port')
PRINTER_IP=$(bashio::config 'printer_ip')
# bashio::config on list values outputs NDJSON (one object per line)
# which isn't valid JSON. Use jq on the options file to get a real array.
PRINTERS_JSON=$(jq -c '.printers // []' /data/options.json 2>/dev/null || echo '[]')

if [[ -z "${API_KEY}" ]]; then
    bashio::log.info "No api_key configured — generating one automatically..."
    API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

    # Read current options, inject key, persist via Supervisor API
    UPDATED=$(jq -c --arg k "${API_KEY}" '.api_key = $k' /data/options.json)
    RESP=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"options\": ${UPDATED}}" \
        http://supervisor/addons/self/options)

    if [[ "${RESP}" == "200" ]]; then
        bashio::log.info "API key generated and saved."
        bashio::log.info "Copy it from: Settings > Add-ons > ESC/POS Print Proxy > Configuration tab."
    else
        bashio::log.fatal "Failed to save auto-generated key (HTTP ${RESP}). Set api_key manually."
        exit 2
    fi
fi

if [[ -n "${PRINTER_IP}" ]]; then
    bashio::log.info "Default printer IP: ${PRINTER_IP} (used when request omits printer_ip/printer_label)"
else
    bashio::log.warning "No default printer_ip set. Callers must provide printer_label or printer_ip per /print request."
fi

# Log labeled-printers count (label→IP resolution happens in Python).
PRINTERS_COUNT=$(echo "$PRINTERS_JSON" | jq 'length' 2>/dev/null || echo "0")
if [[ "${PRINTERS_COUNT}" != "0" && -n "${PRINTERS_COUNT}" ]]; then
    bashio::log.info "Labeled printers configured: ${PRINTERS_COUNT}"
fi

bashio::log.info "Starting ESC/POS print proxy on :${PORT}"

export API_KEY PORT PRINTER_IP PRINTERS_JSON

cd /app
exec python3 print_proxy.py
