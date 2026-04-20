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
# shared/typescript re-exported via apps/web/lib/types.ts ('../../../packages/shared/typescript')
COPY packages/shared /packages/shared
# NEXT_PUBLIC_* переменные Next.js инлайнит в client bundle в момент
# `next build`. compose-level env_file/environment действуют только в
# runtime и до build-stage не доходят — именно поэтому у билдов в prod
# USE_MOCK_API=true пробрасывался дефолтом и mock-слой перехватывал
# реальные запросы (#51.2). Прокидываем нужные NEXT_PUBLIC_* как ARG +
# ENV, а значения передаёт docker-compose.prod.*.yml через build.args.
ARG NEXT_PUBLIC_USE_MOCK_API=false
ARG NEXT_PUBLIC_API_BASE_URL=https://api.aicode9.ru
ENV NEXT_PUBLIC_USE_MOCK_API=${NEXT_PUBLIC_USE_MOCK_API}
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
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
