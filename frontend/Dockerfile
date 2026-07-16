# # Build Stage
# FROM node:18-alpine AS build

# # Set the working directory for the build stage
# WORKDIR /app

# # Copy package.json and package-lock.json
# COPY package*.json ./

# # Install dependencies
# RUN npm install


# # Copy all the source code
# COPY . .

# # Build the app for production
# RUN npm run build

# # Production Stage
# FROM nginx:stable-alpine AS production

# # Copy the build output from the build stage
# COPY --from=build /app/dist /usr/share/nginx/html
# COPY nginx-spa.conf /etc/nginx/conf.d/default.conf
# # Expose the port the app will run on
# EXPOSE 80

# # Start Nginx to serve the production build
# CMD ["nginx", "-g", "daemon off;"]

# frontend/Dockerfile
# -------------------
# Two-stage build:
#   Stage 1 (build)  — Node 18, installs deps, builds Vite app
#   Stage 2 (serve)  — Nginx alpine, serves the static dist folder
#
# VITE_API_URL must be passed at build time so Vite can bake it into the JS bundle.
# Example:
#   docker build --build-arg VITE_API_URL=https://api.example.com -t frontend .

# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM node:18-alpine AS build

WORKDIR /app

# Install dependencies (separate layer for cache efficiency)
COPY package*.json ./
RUN npm install

# Accept the API URL as a build argument and expose it as an env var
# so Vite picks it up during the build step
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

# Copy source and build
COPY . .
RUN npm run build

# ── Stage 2: Serve ────────────────────────────────────────────────────────────
FROM nginx:stable-alpine AS production

# Copy the compiled static files
COPY --from=build /app/dist /usr/share/nginx/html

# Copy the SPA nginx config — handles /session/* and other client-side routes
COPY nginx-spa.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
