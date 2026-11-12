FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG APP_VERSION=dev
ENV VITE_APP_VERSION=$APP_VERSION
RUN npm run build

# Runs as uid 101 (the base image's nginx user), not 10001: see docs/runtime-contract.md
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx/default.conf.template nginx/api-proxy.locations.template /etc/nginx/templates/
COPY --chmod=755 nginx/40-api-proxy.sh /docker-entrypoint.d/
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
