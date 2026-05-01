#!/bin/bash
# Run once on the VPS to configure the firewall.
# Requires ufw and sudo/root.
set -e

ufw default deny incoming
ufw default allow outgoing

ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # Caddy HTTP → HTTPS redirect
ufw allow 443/tcp   # Caddy HTTPS
ufw allow 443/udp   # HTTP/3

# frp tunnel control port — token is the only defence when open to the world.
# REQUIRED: FRP_TOKEN must be generated with: openssl rand -hex 32
# If your home IP is static, restrict to it instead:
#   ufw allow from YOUR_HOME_IP to any port 7000
ufw allow 7000/tcp

ufw --force enable
ufw status verbose
