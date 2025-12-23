FROM nginx:alpine

# Install envsubst for environment variable substitution
RUN apk add --no-cache gettext

ARG NGINX_CONF=nginx.local.conf
COPY ${NGINX_CONF} /etc/nginx/nginx.conf

# Expose ports
EXPOSE 80 443
