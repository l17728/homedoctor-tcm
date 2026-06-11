#!/bin/bash
set -e
echo "=== 家庭医生 · 启动 ==="
# Check dependencies
command -v docker >/dev/null 2>&1 || { echo "ERROR: Docker not installed"; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo "ERROR: Docker Compose not installed"; exit 1; }

# Build and start
docker compose build
docker compose up -d

# Wait for API health
echo "Waiting for API..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "✓ API ready"
        break
    fi
    sleep 1
done

# Wait for frontend
echo "Waiting for frontend..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:3000 > /dev/null 2>&1; then
        echo "✓ Frontend ready"
        break
    fi
    sleep 1
done

echo ""
echo "=== 家庭医生已启动 ==="
echo "前端: http://localhost:3000"
echo "API:  http://localhost:8000"
echo "API文档: http://localhost:8000/docs"
