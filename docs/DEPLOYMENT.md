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

**API 进程数**：当前 SQLite 部署要求 API 保持单进程。不要为 Uvicorn 添加 `--workers`，也不要横向扩展多个 API 副本；每个进程都会启动自己的巡检、维护和周摘要调度任务，多个进程会重复执行这些任务。

**数据持久化**：`data/` 目录是 named Docker volume，镜像更新不影响数据。

**数据库真实路径（重要）**：
- **本地原生部署**：DB 实际位于 `backend\data\homedoctor.db`（uvicorn 以 `backend/` 为工作目录，相对路径 `data/homedoctor.db` 解析于此），**不在仓库根目录 `./data`**。
- **Docker 部署**：DB 在 named volume `app-data` 内（宿主机实际路径为 `/var/lib/docker/volumes/<project>_app-data/_data/homedoctor.db`，可用 `docker volume inspect` 查询），**不是宿主机 repo 下的 `./data`**。宿主机 `./data` 下的备份/清理命令不会命中 volume 内文件。

### 方式二：本地开发部署

```bash
# 后端
cd backend
pip install -c constraints.txt -r requirements.txt
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

**管理员账号初始化**：应用按用户名把 `admin` 和环境变量 `ADMIN_USERS` 中列出的账号赋予管理员角色。首次注册此类用户名时，必须配置 `ADMIN_BOOTSTRAP_TOKEN` 并在注册请求中传入 `admin_bootstrap_token`；任一管理员账号创建后，该令牌不能再创建管理员。请先在可信内网完成初始化，之后从部署环境移除令牌。已有管理员仍按原用户名登录。

**浏览器推送（可选）**：运行 `backend/scripts/generate_vapid_keys.py` 生成一对 VAPID 密钥，将输出设置为 `PUSH_VAPID_PUBLIC_KEY` 与 `PUSH_VAPID_PRIVATE_KEY`，并将 `PUSH_VAPID_SUBJECT` 设为可联系的 `mailto:` 地址。私钥只放在部署环境密钥中，不能提交到仓库或写入数据库。安装依赖后，用户可在“设置 → 浏览器推送”自行订阅。浏览器必须支持 Service Worker/Web Push，站点需使用 HTTPS（localhost 开发例外）；推送发送要求应用主机可向浏览器厂商提供的 HTTPS push endpoint 出站访问。未配置密钥时界面会隐藏可用操作并保留站内通知。取消订阅会删除该用户对应设备的服务端订阅。

- [ ] **设置 SECRET_KEY**：`docker-compose.yml` → `HOMEDOCTOR_SECRET_KEY` 使用随机 32+ 字符。轮换时先设置 `DB_ENCRYPTION_KEY` 为独立、长期保存的备份口令；部署新 `SECRET_KEY` 的同时临时设置 `HOMEDOCTOR_PREVIOUS_SECRET_KEY` 为旧值。启动会将旧明文及旧密钥加密的模型 API 密钥重加密为新密钥；核对模型可用后移除 `HOMEDOCTOR_PREVIOUS_SECRET_KEY`。密钥轮换会使现有 JWT 失效。若历史备份由旧 `SECRET_KEY` 加密，在完成恢复验证或重加密备份前保留 `HOMEDOCTOR_PREVIOUS_SECRET_KEY`；若轮换的是 `DB_ENCRYPTION_KEY`，临时设置 `HOMEDOCTOR_PREVIOUS_DB_ENCRYPTION_KEY`，恢复端点会依次尝试当前和旧密钥。先保存旧密钥并验证备份，再安排轮换。
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

- [ ] **前端 chunk 分割**：`vite.config.ts` 已启用 `manualChunks` 函数化 vendor 分块（react/antd 独立 chunk；知识图谱页按需加载 G6 使用的扩展，首屏 455KB gzip）
- [ ] **gzip 压缩**：nginx 启用 `gzip on`
- [ ] **缓存头**：静态资源配置 `Cache-Control`
- [ ] **数据库索引**：确认 FTS5 索引正常

---

## 备份与恢复

### 备份

```bash
# 通过应用 CLI 创建一致性快照并加密；不要直接用标准 sqlite3 读取 SQLCipher 数据库
docker compose exec -T api python3 cli.py backup:create \
  --username "$HOMEDOCTOR_BACKUP_USERNAME" \
  --password "$HOMEDOCTOR_BACKUP_PASSWORD"
```

命令会调用管理员备份 API，输出加密的 `backup_*.db.enc`。将 `HOMEDOCTOR_BACKUP_USERNAME` 和 `HOMEDOCTOR_BACKUP_PASSWORD` 放在仅 root 可读的主机凭据文件中（例如 `chmod 600 /etc/homedoctor-backup.env`），执行前加载该文件。不要将密码写进仓库或公开的 crontab。

### 恢复

**首选：应用内恢复（推荐）** — `POST /api/backup/restore`（或 CLI `python3 cli.py backup:restore FILE --username USER --password PASS`）已实现完整性校验 + 原子换库（`.restore_pending` → 重启时应用），无需手动拷贝文件。

**手动恢复（仅在应用内恢复不可用时）**：

```bash
# 停服
docker compose stop api

# ★ 必须先删除 WAL/SHM 边车文件，否则旧 WAL 重放会导致数据回退或 malformed database
docker compose exec -T api sh -c "rm -f data/homedoctor.db-wal data/homedoctor.db-shm"

# 替换数据库
docker compose cp backup_20260612.db api:/app/data/homedoctor.db

# 重启
docker compose start api
```

> 注意：SQLite WAL 模式下主库文件旁会存在 `homedoctor.db-wal`（未合并写入日志）与 `homedoctor.db-shm`（共享内存索引）。只替换主库而不删边车文件，SQLite 启动时会将旧 WAL 重放到新库上，造成数据回退或 `database disk image is malformed`。本地原生部署同理：替换 `backend\data\homedoctor.db` 前先删 `backend\data\homedoctor.db-wal` 与 `-shm`。

### 定时备份（crontab）

```bash
# 每日凌晨 3 点备份，保留最近 30 天；先加载 root-only 凭据文件。
# 用 cron 的 shell 执行时，以下命令应写在同一行：
0 3 * * * cd /path/to/homedoctor && set -a && . /etc/homedoctor-backup.env && set +a && docker compose exec -T api python3 cli.py backup:create --username "$HOMEDOCTOR_BACKUP_USERNAME" --password "$HOMEDOCTOR_BACKUP_PASSWORD" >> /var/log/homedoctor-backup.log 2>&1 && find /path/to/homedoctor/backups -type f -name 'backup_*.db.enc' -mtime +30 -delete
```

> 备份 API 将加密文件写入 `HOMEDOCTOR_BACKUP_DIR`。Compose 将该路径设为 `/app/backups` 并挂载到宿主机 `./backups`，所以保留策略应在宿主机清理 `./backups` 中的 `backup_*.db.enc`。不要用标准 `sqlite3.connect` 或直接拷贝运行中的数据库文件替代此命令：两者都绕过 SQLCipher/在线快照与应用层备份加密。

### 备份外置

备份留在 `app-data` volume 内有两个风险：① 与主库同盘，磁盘故障时备份与数据同归于尽；② 容器重建/卷误删时备份一起丢失。建议将备份单独 bind mount 到宿主机目录：

Compose 已将宿主机 `./backups` 挂载到容器 `/app/backups`，并设置 `HOMEDOCTOR_BACKUP_DIR=/app/backups`。应用内手动备份会写入该目录；备份列表同时兼容读取数据库目录中的旧备份，恢复文件仍会暂存到数据库目录供重启时应用。

```bash
mkdir -p backups   # 宿主机执行一次
# Compose 已配置 /app/backups；通过应用 API 创建加密备份，沿用上面的 CLI 命令
docker compose exec -T api python3 cli.py backup:create \
  --username "$HOMEDOCTOR_BACKUP_USERNAME" \
  --password "$HOMEDOCTOR_BACKUP_PASSWORD"
# 宿主机定期清理卷外加密备份
find /path/to/homedoctor/backups -type f -name 'backup_*.db.enc' -mtime +30 -delete
```

卷外 `./backups/` 目录建议再纳入主机级备份（rsync 到异地/NAS）。

本地原生部署的真实数据库路径是 `backend/data/homedoctor.db`；仓库根目录 `data/` 不作为运行数据库目录。

### 反向代理来源 IP

限流默认只信任回环地址上的代理。若 API 位于 Nginx/Traefik 后，设置 `HOMEDOCTOR_TRUSTED_PROXY_IPS` 为代理容器的固定 IP 或专用 Docker 子网（逗号分隔的 IP/CIDR），例如 `172.22.0.2,172.22.0.0/24`。不要配置整个公网网段；非可信来源的 `X-Forwarded-For` 会被忽略。

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
