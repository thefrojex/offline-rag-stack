#!/bin/sh
# The edge container exists only because Docker cannot publish a port from an
# `internal: true` network. It joins that network plus a host-facing one and
# relays TCP to the API. To keep it from being a way out, it drops every
# outbound packet that is not loopback, a reply, or headed for the internal subnet.
set -eu

INTERNAL_CIDR="${INTERNAL_CIDR:-10.231.10.0/24}"
UPSTREAM="${UPSTREAM:-rag-api:8000}"

iptables -P OUTPUT DROP
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -d "$INTERNAL_CIDR" -j ACCEPT

echo "edge: egress locked to $INTERNAL_CIDR, relaying :8000 -> $UPSTREAM"
exec socat TCP-LISTEN:8000,fork,reuseaddr "TCP:$UPSTREAM"
