# Stage-only build recipe. No registry push, secrets or provider provisioning.
# Pin upstream base-image digests before production release certification.
FROM node:24-bookworm-slim AS builder
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /srv/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

FROM node:24-bookworm-slim AS web
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /srv/web
COPY --from=builder --chown=node:node /srv/web/ /srv/web/
USER node
EXPOSE 3000
CMD ["./node_modules/.bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
