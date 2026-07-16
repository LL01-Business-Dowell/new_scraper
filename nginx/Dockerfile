# FROM nginx:1.23.3-alpine
# COPY ./nginx.conf /etc/nginx/conf.d/default.conf
# EXPOSE 80
# EXPOSE 443
# CMD ["nginx", "-g", "daemon off;"]

# nginx/Dockerfile
# ----------------
# Reverse proxy — routes traffic to backend and frontend containers.
# SSL termination handled here using Let's Encrypt certificates.
# No changes needed from original.

FROM nginx:1.23.3-alpine
COPY ./nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
EXPOSE 443
CMD ["nginx", "-g", "daemon off;"]
