# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN chown -R node:node /app
USER node
RUN npm ci
COPY --chown=node:node . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:8080/ || exit 1
