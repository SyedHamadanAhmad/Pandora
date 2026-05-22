#!/usr/bin/env bash
# Phase 2 manual gate — see docs/PHASE_2.md Step 11
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
COOKIE_JAR="${COOKIE_JAR:-/tmp/pandora-cookies.txt}"
EMAIL="${EMAIL:-dev-$(date +%s)@example.com}"
PASSWORD="${PASSWORD:-secret123}"
IMAGE_FILE="${IMAGE_FILE:-}"

echo "==> Phase 2 gate"
echo "    BASE_URL=$BASE_URL"
echo "    EMAIL=$EMAIL"
echo "    COOKIE_JAR=$COOKIE_JAR"

if ! curl -sf "$BASE_URL/health" >/dev/null; then
  echo "ERROR: Cannot reach $BASE_URL/health"
  echo ""
  echo "If backend has no published port, use one of:"
  echo "  1. make dev   (docker-compose.dev.yml maps 8000:8000)"
  echo "  2. BASE_URL=http://127.0.0.1:8000 docker compose exec backend ./scripts/phase2_gate.sh"
  echo "  3. See docs/PHASE_2.md — Verifying the API"
  exit 1
fi

echo "==> Register"
curl -sS -X POST "$BASE_URL/api/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}"
echo ""

echo "==> Login"
curl -sS -c "$COOKIE_JAR" -X POST "$BASE_URL/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}"
echo ""

echo "==> Create project"
PROJECT_JSON=$(curl -sS -b "$COOKIE_JAR" -X POST "$BASE_URL/api/projects/" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Phase 2 gate project"}')
echo "$PROJECT_JSON"
PROJECT_ID=$(python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" <<<"$PROJECT_JSON")

THREAD_ARGS=(
  -sS -b "$COOKIE_JAR"
  -X POST "$BASE_URL/api/projects/$PROJECT_ID/thread/"
  -F 'content=Modern SaaS dashboard'
  -F 'urls=["https://example.com"]'
)
if [[ -n "$IMAGE_FILE" && -f "$IMAGE_FILE" ]]; then
  THREAD_ARGS+=(-F "images=@$IMAGE_FILE")
else
  # Minimal valid PNG if no file provided
  TMPPNG=$(mktemp /tmp/pandora-gate-XXXXXX.png)
  printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89' >"$TMPPNG"
  THREAD_ARGS+=(-F "images=@$TMPPNG")
  trap 'rm -f "$TMPPNG"' EXIT
fi

echo "==> Post thread (multipart)"
curl "${THREAD_ARGS[@]}"
echo ""

echo "==> List thread"
curl -sS -b "$COOKIE_JAR" "$BASE_URL/api/projects/$PROJECT_ID/thread/"
echo ""

echo "==> Components (empty)"
curl -sS -b "$COOKIE_JAR" "$BASE_URL/api/projects/$PROJECT_ID/components"
echo ""

echo "==> Logout"
curl -sS -b "$COOKIE_JAR" -o /dev/null -w "HTTP %{http_code}\n" \
  -X POST "$BASE_URL/api/auth/logout"
echo ""

echo "==> Gate script finished. Also check:"
echo "    - MinIO console: http://localhost:9001 (bucket pandora-images)"
echo "    - RabbitMQ: no new messages on pandora.parse.* (Phase 3 only)"
echo "    - OpenAPI: $BASE_URL/docs (when using make dev)"
