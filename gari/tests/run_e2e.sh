#!/bin/bash
cd "$(dirname "$0")/.."; pkill -f "python3 app.py" 2>/dev/null; sleep 0.5; rm -f /tmp/e2e.db*
GARI_DB=/tmp/e2e.db GARI_SECRET=e2e-secret-e2e-secret-e2e-secret PORT=5055 python3 app.py > /tmp/server.log 2>&1 &
SRV=$!; for i in $(seq 1 20); do curl -s localhost:5055/api/health >/dev/null && break; sleep 0.3; done
timeout 250 python3 tests/e2e.py; RC=$?; kill $SRV 2>/dev/null; exit $RC
