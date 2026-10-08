FROM alpine:3.21
RUN apk add --no-cache iptables socat
COPY docker/edge-entrypoint.sh /usr/local/bin/edge-entrypoint.sh
RUN chmod +x /usr/local/bin/edge-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/edge-entrypoint.sh"]
