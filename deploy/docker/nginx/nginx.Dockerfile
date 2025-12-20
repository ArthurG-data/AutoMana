FROM nginx:alpine

# Install envsubst for environment variable substitution
RUN apk add --no-cache gettext

COPY nginx.local.conf /etc/nginx/nginx.conf

# Expose ports
EXPOSE 80 443
