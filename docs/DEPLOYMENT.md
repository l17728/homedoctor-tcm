# Deployment Guide — 家庭医生

## 部署方式

### 方式一：Docker Compose（推荐）

**前置条件**：Docker 20+ 和 Docker Compose v2+

```bash
# 一键启动
./start.sh

# 或手动
docker compose build
docker compose up -d
```

**服务端口**：
| 服务 | 端口 | 说明 |
|------|------|------|
| Frontend (nginx) | 3000 | React SPA + /api 反向代理 |
| Backend (uvicorn) | 8000 | FastAPI |

**数据持久化**：`data/` 目录是 named Docker volume，镜像更新不影响数据。

### 方式二：本地开发部署

```bash
# 后端
cd backend
pip install -r requirements.txt
python3 scripts/seed_herbs_batch1.py
python3 scripts/seed_herbs_batch2.py
python3 scripts/seed_herbs_batch3.py
python3 scripts/seed_formulas.py
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 前端
cd frontend
npm install
npm run build
# 用 nginx 或其他服务器托管 dist/
```

### 方式三：反向代理部署

已有 nginx 的服务器，将前端构建产物放入 web root：

```bash
cd frontend && npm run build
cp -r dist/* /var/www/homedoctor/
```

nginx 配置（参考 `frontend/nginx.conf`）：
```nginx
server {
    listen 80;
    root /var/www/homedoctor;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

---

## 生产环境 Checklist

### 安全配置（必做）

- [ ] **修改 SECRET_KEY**：`docker-compose.yml` → `HOMEDOCTOR_SECRET_KEY` 改为随机 32+ 字符
- [ ] **修改 JWT 过期时间**：`config.py` → `ACCESS_TOKEN_EXPIRE_MINUTES`
- [ ] **配置 CORS**：`config.py` → `ALLOWED_ORIGINS` 设为实际域名
- [ ] **启用 HTTPS**：nginx 配置 SSL 证书
- [ ] **数据库加密**：启用 SQLCipher（`pip install pysqlcipher3`）
- [ ] **限制端口暴露**：生产环境只暴露前端端口（3000/80），后端只在内部网络

### 数据

- [ ] **种子数据**：首次启动确认 203 中药 + 82 方剂已加载
- [ ] **安全规则**：确认 60+ 配伍禁忌规则已在数据库
- [ ] **备份策略**：配置定时 SQLite 备份（每日）
- [ ] **备份验证**：恢复测试（在测试环境验证备份可用）

### 功能验证

```bash
# 冒烟测试
./smoke_test.sh

# 手动验证清单
# 1. 访问 http://YOUR_HOST:3000 → 看到登录页
# 2. 注册新用户 → 跳转首页
# 3. 搜索"黄芪" → 显示详情
# 4. AI 对话 → 输入"心梗" → 看到安全警告
# 5. 体质自测 → 完成 66 题 → 看到结果
# 6. 创建提醒 → 今日提醒显示
# 7. 切换长辈模式 → 3 Tab 界面
```

### 性能

- [ ] **前端 chunk 分割**：`vite.config.ts` → `manualChunks`（当前 1.3MB 单 chunk）
- [ ] **gzip 压缩**：nginx 启用 `gzip on`
- [ ] **缓存头**：静态资源配置 `Cache-Control`
- [ ] **数据库索引**：确认 FTS5 索引正常

---

## 备份与恢复

### 备份

```bash
# 方法一：SQLite .backup()（在线备份，不锁库）
docker compose exec api python3 -c "
import sqlite3
src = sqlite3.connect('data/homedoctor.db')
dst = sqlite3.connect('data/backup_$(date +%Y%m%d).db')
src.backup(dst)
dst.close()
src.close()
print('备份完成')
"

# 方法二：直接拷贝（需停服）
docker compose stop api
cp data/homedoctor.db data/homedoctor.db.bak
docker compose start api
```

### 恢复

```bash
# 停服
docker compose stop api

# 替换数据库
cp data/backup_20260612.db data/homedoctor.db

# 重启
docker compose start api
```

### 定时备份（crontab）

```bash
# 每日凌晨 3 点自动备份，保留最近 30 天
0 3 * * * cd /path/to/homedoctor && docker compose exec -T api python3 -c "
import sqlite3, datetime
src = sqlite3.connect('data/homedoctor.db')
dst = sqlite3.connect(f'data/backup_{datetime.date.today().isoformat()}.db')
src.backup(dst)
dst.close(); src.close()
" && find data/backup_*.db -mtime +30 -delete
```

---

## 更新部署

```bash
# 拉取最新代码
git pull origin main

# 重新构建并启动（data/ 不受影响）
docker compose build
docker compose up -d

# 验证
./smoke_test.sh
```

**关键**：`data/` 是 named volume，`docker compose up` 不会删除数据。

### 致命错误防范

| # | 场景 | 预防 |
|---|------|------|
| F1 | rsync --delete 覆盖 data/ | 部署脚本硬编码 `--exclude='data/'` |
| F2 | git archive 只含已提交文件 | 部署前必须 `git commit` |
| F3 | 数据库迁移丢数据 | 不用 ALTER TABLE，字段加在 JSON properties |
| F4 | AI 幻觉绕过安全层 | 硬编码层在 AI 层之前运行 |

---

## 监控

### 健康检查

```bash
# API 健康检查
curl http://localhost:8000/api/health
# → {"status": "healthy"}

# Docker 健康检查
docker compose ps
```

### 日志

```bash
# 实时日志
docker compose logs -f api
docker compose logs -f frontend

# 最近 100 行
docker compose logs --tail 100 api
```

---

## 故障排除

| 问题 | 解决方案 |
|------|---------|
| 前端 502 | 检查后端是否运行：`docker compose ps api` |
| 数据库锁定 | 重启 API：`docker compose restart api` |
| 种子数据丢失 | 重新运行种子脚本（INSERT OR IGNORE 安全） |
| 登录失败 | 检查 SECRET_KEY 是否一致（JWT 签名不匹配） |
| 搜索无结果 | 检查 FTS5 表：`SELECT * FROM herbs_fts` |
| CORS 错误 | 检查 `ALLOWED_ORIGINS` 配置 |
