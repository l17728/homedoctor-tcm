# 家庭医生 · 一键备份迁移部署脚本
# 从生产服务器(124.156.193.122 Docker volume)备份数据库 → 下载 → 本地备份 → 替换 → 重启部署
# 用法: powershell -ExecutionPolicy Bypass -File backup-migrate.ps1
#
# 原则 (AGENTS.md §1.5 部署绝不删数据):
#   - 服务器端保留时间戳备份 (~/homedoctor-backups/)
#   - 本地替换前先备份到 backups/local-before-migrate-<ts>.db
#   - 使用 SQLite backup API 保证一致性 (不用裸文件拷贝)

param(
    [string]$Server = '124.156.193.122',
    [string]$User = 'root',
    [string]$RemoteDb = '/var/lib/docker/volumes/homedoctor_app-data/_data/homedoctor.db'
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backupDir = Join-Path $root 'backups'
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$remoteBackup = "/root/homedoctor-backups/homedoctor-$ts.db"
$localProdDb = Join-Path $backupDir "homedoctor-prod-$ts.db"
$localDb = Join-Path $root 'backend\data\homedoctor.db'

Write-Host "[1/6] 服务器端备份 (SQLite backup API + WAL checkpoint) ..."
$py = @"
import sqlite3, os
src = '$RemoteDb'
dst = '/root/homedoctor-backups/homedoctor-$ts.db'
os.makedirs(os.path.dirname(dst), exist_ok=True)
s = sqlite3.connect(src)
s.execute('PRAGMA wal_checkpoint(TRUNCATE)')
d = sqlite3.connect(dst)
s.backup(d)
d.close(); s.close()
print('SERVER_BACKUP_OK', dst)
"@
$pyPath = Join-Path $env:TEMP "hd-migrate-$ts.py"
[System.IO.File]::WriteAllText($pyPath, $py, (New-Object System.Text.UTF8Encoding($false)))
& ssh -o BatchMode=yes "${User}@${Server}" "mkdir -p /root/homedoctor-backups"
if ($LASTEXITCODE -ne 0) { throw 'SSH 连接失败（检查免密登录）' }
& scp -o BatchMode=yes $pyPath "${User}@${Server}:/tmp/hd-migrate.py"
if ($LASTEXITCODE -ne 0) { throw '上传迁移脚本失败' }
& ssh -o BatchMode=yes "${User}@${Server}" "python3 /tmp/hd-migrate.py && rm -f /tmp/hd-migrate.py"
if ($LASTEXITCODE -ne 0) { throw '服务器端备份失败' }

Write-Host "[2/6] 下载数据库 ($remoteBackup) ..."
& scp -o BatchMode=yes "${User}@${Server}:$remoteBackup" $localProdDb
if ($LASTEXITCODE -ne 0) { throw '下载数据库失败' }
$size = [math]::Round((Get-Item $localProdDb).Length / 1MB, 1)
Write-Host "    已下载 $localProdDb ($size MB)"

Write-Host "[3/6] 停止本地服务 ..."
& powershell -ExecutionPolicy Bypass -File (Join-Path $root 'stop-local.ps1')

Write-Host "[4/6] 备份本地当前数据库 (SQLite backup API, 含 WAL 未落盘数据) ..."
if (Test-Path $localDb) {
    $localBak = Join-Path $backupDir "local-before-migrate-$ts.db"
    $bakPy = @"
import sqlite3
src = sqlite3.connect(r'$localDb')
dst = sqlite3.connect(r'$localBak')
src.backup(dst)
dst.close(); src.close()
print('LOCAL_BACKUP_OK')
"@
    & (Join-Path $root 'backend\.venv\Scripts\python.exe') -c $bakPy
    if ($LASTEXITCODE -ne 0) { throw '本地备份失败（SQLite backup API）' }
    Write-Host "    已备份 → backups/local-before-migrate-$ts.db"
}

Write-Host "[5/6] 替换数据库并重启部署 ..."
Copy-Item $localProdDb $localDb -Force
Remove-Item "$localDb-wal", "$localDb-shm" -Force -ErrorAction SilentlyContinue
& powershell -ExecutionPolicy Bypass -File (Join-Path $root 'start-local.ps1') -SkipBuild
if ($LASTEXITCODE -ne 0) { throw '重启失败，可从 backups/ 恢复' }

Write-Host "[6/6] 验证 ..."
Start-Sleep -Seconds 3
$health = Invoke-RestMethod -Uri 'http://127.0.0.1:7459/api/health' -TimeoutSec 10
Write-Host "    API 健康: $($health.status)"
Write-Host ''
Write-Host '=== 迁移完成 ==='
Write-Host "本地库:   backend\data\homedoctor.db"
Write-Host "本地备份: backups\local-before-migrate-$ts.db"
Write-Host "服务器备份: $remoteBackup"
Write-Host '如需回滚: 停止服务后用 backups\local-before-migrate-*.db 覆盖 backend\data\homedoctor.db 再重启'
