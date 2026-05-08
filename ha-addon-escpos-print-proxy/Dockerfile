ARG BUILD_FROM
FROM $BUILD_FROM

# Home Assistant add-on bases for ARCH in {amd64,aarch64,armv7}:
#   ghcr.io/home-assistant/${BUILD_ARCH}-base-python:3.11-alpine3.19
# Already ships Python 3.11 + bashio. We add Flask, Pillow, requests.

ENV LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Pillow needs libjpeg/zlib at runtime; alpine base doesn't preinstall them.
RUN apk add --no-cache \
        jq \
        libjpeg-turbo \
        zlib \
    && apk add --no-cache --virtual .build-deps \
        build-base \
        jpeg-dev \
        zlib-dev \
    && pip3 install --no-cache-dir \
        "Flask>=3.0,<4.0" \
        "Pillow>=10.0,<12.0" \
    && apk del .build-deps

WORKDIR /app
COPY print_proxy.py escpos_min.py ./
COPY run.sh /run.sh
RUN chmod a+x /run.sh

# Health check: /status is unauthenticated and cheap.
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget --quiet --tries=1 --spider "http://localhost:${PORT:-8073}/status" || exit 1

CMD ["/run.sh"]
