# ── Stage 1: Base & Dependencies ──────────────────────────────────────────────
FROM node:18-alpine AS development

WORKDIR /app

# Install dependencies (separate layer for cache efficiency)
COPY package*.json ./
RUN npm install

# Copy source code
COPY . .

# Accept the API URL as an environment variable for local dev runtime
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

EXPOSE 5173

# Default command for development hot-reloading
CMD ["npm", "run", "dev"]

# ── Stage 2: Build (Production Only) ──────────────────────────────────────────
FROM node:18-alpine AS build

WORKDIR /app

# Re-use the dependency layout or build cleanly
COPY package*.json ./
RUN npm install
COPY . .

ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# ── Stage 3: Serve (Production Only) ──────────────────────────────────────────
FROM nginx:stable-alpine AS production

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx-spa.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]