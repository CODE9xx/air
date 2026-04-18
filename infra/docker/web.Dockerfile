# =============================================================================
# Code9 Web (Next.js 14) — multi-stage
# =============================================================================

ARG NODE_VERSION=20-alpine

FROM node:${NODE_VERSION} AS base
ENV CI=true
WORKDIR /app
RUN apk add --no-cache libc6-compat

# --- deps ---
FROM base AS deps
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# --- dev: исходники монтируются через volume ---
FROM deps AS dev
ENV NODE_ENV=development
EXPOSE 3000
CMD ["npm", "run", "dev"]

# --- build: готовим production-артефакт ---
FROM deps AS build
COPY apps/web .
RUN npm run build

# --- prod: минимальный рантайм ---
FROM node:${NODE_VERSION} AS prod
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/next.config.mjs ./next.config.mjs
EXPOSE 3000
CMD ["npm", "run", "start"]
