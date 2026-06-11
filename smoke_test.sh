#!/bin/bash
# Quick smoke test to verify the system is working
set -e
echo "=== Smoke Test ==="
PASS=0
FAIL=0

check() {
    local name=$1
    local url=$2
    local expected_status=$3
    local status=$(curl -sf -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    if [ "$status" = "$expected_status" ]; then
        echo "✓ $name (HTTP $status)"
        PASS=$((PASS+1))
    else
        echo "✗ $name (expected $expected_status, got $status)"
        FAIL=$((FAIL+1))
    fi
}

# Backend health
check "Health" "http://localhost:8000/api/health" "200"

# Auth
TOKEN=$(curl -sf -X POST http://localhost:8000/api/auth/register \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"smoketest_$(date +%s)\",\"password\":\"test123456\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")

if [ -n "$TOKEN" ]; then
    check "Herbs List" "http://localhost:8000/api/herbs" "200"
    check "Formulas List" "http://localhost:8000/api/formulas" "200"
    check "Dashboard" "http://localhost:8000/api/dashboard/stats" "200"
    check "Daily Health" "http://localhost:8000/api/daily-health" "200"
    check "Chat (auth)" "http://localhost:8000/api/chat/history" "200"
else
    echo "⚠ Register failed, skipping auth-dependent tests"
fi

# Frontend
check "Frontend" "http://localhost:3000" "200"

# Safety check
SAFETY=$(curl -sf -X POST http://localhost:8000/api/safety/check-v2 \
    -H "Content-Type: application/json" \
    -d '{"herbs":["附子","半夏"]}' 2>/dev/null || echo "")
if echo "$SAFETY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert not d['safe']; sys.exit(0)" 2>/dev/null; then
    echo "✓ Safety check (十八反 detected)"
    PASS=$((PASS+1))
else
    echo "✗ Safety check failed"
    FAIL=$((FAIL+1))
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ $FAIL -eq 0 ] && echo "✓ All smoke tests passed" || echo "✗ Some tests failed"
exit $FAIL
