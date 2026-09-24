# Imagen de Odoo 20.0 (Community) para desarrollo y CI.
#
# Docker Hub todavía no publica la imagen oficial `odoo:20`, así que se construye
# desde el paquete .deb oficial (nightly.odoo.com) siguiendo la receta de
# https://github.com/odoo/docker (19.0, LGPL-3). Cuando exista la imagen oficial,
# alcanza con reemplazar `build:` por `image: odoo:20` en docker-compose.yml.
FROM ubuntu:noble

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV LANG=C.UTF-8 \
    DEBIAN_FRONTEND=noninteractive

ARG TARGETARCH

# Herramientas base y wkhtmltopdf (reportes PDF), igual que la imagen oficial.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl python3-watchdog \
    && ARCH="${TARGETARCH:-$(dpkg --print-architecture)}" \
    && case "${ARCH}" in \
         amd64) WKHTMLTOPDF_SHA1=967390a759707337b46d1c02452e2bb6b2dc6d59 ;; \
         arm64) WKHTMLTOPDF_SHA1=90f6e69896d51ef77339d3f3a20f8582bdf496cc ;; \
         *) echo "Arquitectura no soportada: ${ARCH}" && exit 1 ;; \
       esac \
    && curl -fsSL -o /tmp/wkhtmltox.deb \
       "https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.jammy_${ARCH}.deb" \
    && echo "${WKHTMLTOPDF_SHA1}  /tmp/wkhtmltox.deb" | sha1sum -c - \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && rm -rf /var/lib/apt/lists/* /tmp/wkhtmltox.deb

# Odoo 20.0. Se fija el primer build de la serie: nightly.odoo.com purga los
# builds diarios viejos pero conserva el primero de cada versión.
ENV ODOO_VERSION=20.0
ARG ODOO_RELEASE=20260921
ARG ODOO_SHA256=ec54225a02e3a33f5a26f74617f1b878288608ef0da33a41b1dbc88731f9df82
RUN curl -fsSL -o /tmp/odoo.deb \
       "https://nightly.odoo.com/${ODOO_VERSION}/nightly/deb/odoo_${ODOO_VERSION}.${ODOO_RELEASE}_all.deb" \
    && echo "${ODOO_SHA256}  /tmp/odoo.deb" | sha256sum -c - \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/odoo.deb \
    && rm -rf /var/lib/apt/lists/* /tmp/odoo.deb

RUN mkdir -p /mnt/extra-addons /var/lib/odoo \
    && chown -R odoo:odoo /mnt/extra-addons /var/lib/odoo

ENV ODOO_RC=/etc/odoo/odoo.conf
VOLUME ["/var/lib/odoo"]
EXPOSE 8069 8072

USER odoo
ENTRYPOINT ["odoo"]
