# ---------------------------------------------------------------------------
# LawSchool frontend -- production image.
#
# Stage 1 builds the SPA; stage 2 serves the static bundle with Nginx, including
# the history-mode fallback the React Router needs on a hard refresh.
# ---------------------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /app

# Lockfile first: dependencies are cached unless package.json/lock actually change.
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# VITE_* values are embedded in the bundle at build time and are therefore PUBLIC.
# Only public identifiers belong here -- never an API secret.
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_RAZORPAY_KEY_ID=
ARG VITE_CLOUDFLARE_CUSTOMER_CODE=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_RAZORPAY_KEY_ID=$VITE_RAZORPAY_KEY_ID \
    VITE_CLOUDFLARE_CUSTOMER_CODE=$VITE_CLOUDFLARE_CUSTOMER_CODE

RUN npm run build


# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Static config only; no application code in this layer.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]