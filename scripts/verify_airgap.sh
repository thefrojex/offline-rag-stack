#!/usr/bin/env bash
# Proves the stack has no route to the internet.
#
# 1. A fresh container on the stack's network tries DNS, TCP and HTTP to the outside: all must fail.
# 2. The same probes run inside every running service container: all must fail.
# 3. Two controls show the probes are not simply broken: the probe container CAN reach the API
#    over the internal network, and the same outbound probe on the default bridge succeeds when
#    this host is online.
#
# Exit 0 only if no outbound probe succeeded.
set -uo pipefail

NETWORK="${AIRGAP_NETWORK:-offline-rag-airgap}"
IMAGE="${API_IMAGE:-offline-rag-stack/api:0.1.0}"
COMPOSE=(docker compose)
TARGET_IP="${PROBE_IP:-1.1.1.1}"
TARGET_HOST="${PROBE_HOST:-example.com}"

leaks=0

PROBE_PY=$(cat <<'PY'
import socket, sys, urllib.request
ip, host = sys.argv[1], sys.argv[2]
def tcp():
    socket.create_connection((ip, 443), timeout=4).close()
def dns():
    socket.gethostbyname(host)
def http():
    urllib.request.urlopen(f"http://{ip}", timeout=4)
for name, fn in (("dns", dns), ("tcp", tcp), ("http", http)):
    try:
        fn()
        print(f"{name}=REACHED")
    except urllib.error.HTTPError:
        print(f"{name}=REACHED")  # got an HTTP response, so packets flowed
    except Exception as exc:
        print(f"{name}=blocked ({type(exc).__name__})")
PY
)

report() { # label, probe output
  local label="$1" output="$2"
  if grep -q "REACHED" <<<"$output"; then
    printf '  FAIL  %-22s %s\n' "$label" "$(tr '\n' ' ' <<<"$output")"
    leaks=$((leaks + 1))
  else
    printf '  ok    %-22s %s\n' "$label" "$(tr '\n' ' ' <<<"$output")"
  fi
}

echo "== probe container on $NETWORK (outbound must fail)"
out=$(docker run --rm --network "$NETWORK" --entrypoint python "$IMAGE" -c "$PROBE_PY" "$TARGET_IP" "$TARGET_HOST" 2>&1)
report "fresh container" "$out"

echo "== running services (outbound must fail)"
for service in rag-api ollama qdrant edge; do
  cid=$("${COMPOSE[@]}" ps -q "$service" 2>/dev/null)
  if [ -z "$cid" ]; then
    printf '  skip  %-22s not running\n' "$service"
    continue
  fi
  case "$service" in
    rag-api)
      out=$(docker exec -i "$cid" python -c "$PROBE_PY" "$TARGET_IP" "$TARGET_HOST" 2>&1) ;;
    edge)
      out=$(docker exec "$cid" sh -c "
        getent hosts $TARGET_HOST >/dev/null 2>&1 && echo dns=REACHED || echo dns=blocked
        nc -z -w 4 $TARGET_IP 443 >/dev/null 2>&1 && echo tcp=REACHED || echo tcp=blocked
        wget -q -T 4 -O /dev/null http://$TARGET_IP >/dev/null 2>&1 && echo http=REACHED || echo http=blocked") ;;
    *)
      out=$(docker exec "$cid" bash -c "
        getent hosts $TARGET_HOST >/dev/null 2>&1 && echo dns=REACHED || echo dns=blocked
        timeout 4 bash -c 'exec 3<>/dev/tcp/$TARGET_IP/443' >/dev/null 2>&1 && echo tcp=REACHED || echo tcp=blocked") ;;
  esac
  report "$service" "$out"
done

echo "== controls"
if docker run --rm --network "$NETWORK" --entrypoint python "$IMAGE" -c \
  "import urllib.request; print(urllib.request.urlopen('http://rag-api:8000/livez', timeout=5).status)" 2>/dev/null | grep -q 200; then
  echo "  ok    probe container reaches rag-api:8000 over the internal network"
else
  echo "  WARN  probe container could not reach rag-api (is the stack up?)"
fi
bridge=$(docker run --rm --network bridge --entrypoint python "$IMAGE" -c "$PROBE_PY" "$TARGET_IP" "$TARGET_HOST" 2>&1)
if grep -q "REACHED" <<<"$bridge"; then
  echo "  ok    same probe on the default bridge reaches the internet: $(tr '\n' ' ' <<<"$bridge")"
else
  echo "  note  default bridge is also blocked, so this host looks offline and the control proves nothing"
fi

echo
if [ "$leaks" -eq 0 ]; then
  echo "AIR-GAP VERIFIED: no outbound connection succeeded from any probed container"
else
  echo "AIR-GAP BROKEN: $leaks probe(s) reached the outside" >&2
  exit 1
fi
