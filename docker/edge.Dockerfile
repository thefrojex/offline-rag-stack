FROM alpine:3.21@sha256:ce64758a109eb420d874a118f87920e625e12d3634e03b4a5573fd9f6e5d3507
RUN apk add --no-cache iptables socat
COPY docker/edge-entrypoint.sh /usr/local/bin/edge-entrypoint.sh
RUN chmod +x /usr/local/bin/edge-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/edge-entrypoint.sh"]
