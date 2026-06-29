# ── Bank Statement Scanner — Web Frontend ─────────────────────
# Multi-stage production Dockerfile for Next.js (standalone output)

# Stage 1: Install dependencies
FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci --prefer-offline

# Stage 2: Build the application
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# API_URL controls where Next.js rewrites proxy to.
# In ECS, this is the Cloud Map service discovery address.
ARG API_URL=http://127.0.0.1:8000
ENV API_URL=$API_URL

RUN npm run build

# Stage 3: Production runner (minimal image)
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

# Don't run as root - explicit UID 10001 for SOC2 compliance
RUN addgroup --system --gid 10001 nodejs \
    && adduser --system --uid 10001 nextjs

# Copy standalone output + static assets + public dir
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER 10001:10001

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
