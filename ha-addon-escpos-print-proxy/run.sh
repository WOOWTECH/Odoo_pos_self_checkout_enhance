#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
#
# HA add-on entrypoint. Reads /data/options.json via bashio and execs the
# Flask proxy with the configured API key and port.

set -euo pipefail

API_KEY=$(bashio::config 'api_key')
PORT=$(bashio::config 'port')
PAPER_MM=$(bashio::config 'paper_mm')
PRINTER_IP=$(bashio::config 'printer_ip')
# Pass the labeled-printers list through as raw JSON; print_proxy.py parses it.
PRINTERS_JSON=$(bashio::config 'printers')

if [[ -z "${API_KEY}" ]]; then
    bashio::log.fatal "api_key is empty. Generate one with:  openssl rand -hex 32"
    bashio::log.fatal "Then set it in the add-on Configuration tab."
    exit 2
fi

if [[ -n "${PRINTER_IP}" ]]; then
    bashio::log.info "Default printer IP: ${PRINTER_IP} (used when request omits printer_ip/printer_label)"
else
    bashio::log.warning "No default printer_ip set. Callers must provide printer_label or printer_ip per /print request."
fi

# Log labeled-printers count (label→IP resolution happens in Python).
PRINTERS_COUNT=$(bashio::config 'printers | length')
if [[ "${PRINTERS_COUNT}" != "0" && -n "${PRINTERS_COUNT}" ]]; then
    bashio::log.info "Labeled printers configured: ${PRINTERS_COUNT}"
fi

bashio::log.info "Starting ESC/POS print proxy on :${PORT} (paper=${PAPER_MM}mm)"

export API_KEY PORT PAPER_MM PRINTER_IP PRINTERS_JSON

cd /app
exec python3 print_proxy.py
