#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
#
# HA add-on entrypoint. Reads /data/options.json via bashio and execs the
# Flask proxy with the configured API key and port.

set -euo pipefail

API_KEY=$(bashio::config 'api_key')
PORT=$(bashio::config 'port')
PAPER_MM=$(bashio::config 'paper_mm')

if [[ -z "${API_KEY}" ]]; then
    bashio::log.fatal "api_key is empty. Generate one with:  openssl rand -hex 32"
    bashio::log.fatal "Then set it in the add-on Configuration tab."
    exit 2
fi

bashio::log.info "Starting ESC/POS print proxy on :${PORT} (paper=${PAPER_MM}mm)"

export API_KEY PORT PAPER_MM

cd /app
exec python3 print_proxy.py
