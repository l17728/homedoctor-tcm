# 家庭医生 · 本地原生部署启动脚本（无 Docker）
# 用法: powershell -ExecutionPolicy Bypass -File start-local.ps1 [-SkipBuild]
param(
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$pidFile = Join-Path $logDir 'service-pids.json'

# --- 日志归档（防止 Start-Process -RedirectStandard* 覆盖式丢失历史日志） ---
# 启动前把已有日志改名归档为 <名>-YYYYMMDD-HHmmss.log，仅保留最近 5 个
function Archive-Log {
    param([string]$Name)
    $logPath = Join-Path $logDir $Name
    if (-not (Test-Path $logPath)) { return }
    $base = [IO.Path]::GetFileNameWithoutExtension($Name)
    $ext = [IO.Path]::GetExtension($Name)
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    try {
        Rename-Item -LiteralPath $logPath -NewName "$base-$stamp$ext" -ErrorAction Stop
    } catch {
        Write-Warning "无法归档日志 $Name（可能被占用）：$($_.Exception.Message)"
        return
    }
    $archived = @(Get-ChildItem -Path $logDir -Filter "$base-*$ext" -File |
        Sort-Object Name -Descending)
    if ($archived.Count -gt 5) {
        $archived | Select-Object -Skip 5 | Remove-Item -Force -ErrorAction SilentlyContinue
    }
}

# 端口规划（8000/8001 被本机 llama-server 占用，改用 7459 系列）
$BACKEND_PORT = 7459
$FRONTEND_PORT = 7460

# --- 加载 .env ---
Get-Content (Join-Path $root '.env') | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}

# --- 进程清理（失败兜底：任何一步失败时回收已启动进程，避免孤儿） ---
$script:backendProc = $null
$script:frontendProc = $null
function Stop-StartedProcesses {
    foreach ($p in @($script:frontendProc, $script:backendProc)) {
        if ($p -and -not $p.HasExited) {
            # 连同子进程（node / cmd 壳）一起停止
            Get-CimInstance Win32_Process -Filter "ParentProcessId=$($p.Id)" -ErrorAction SilentlyContinue |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

try {
    # --- 端口预检（前后端一并检查，被占用时拒绝启动） ---
    foreach ($port in $BACKEND_PORT, $FRONTEND_PORT) {
        $portBusy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($portBusy) {
            throw "端口 $port 已被占用（PID $($portBusy[0].OwningProcess)）。请先运行 stop-local.ps1 停止旧实例。"
        }
    }

    Archive-Log 'backend-err.log'
    Archive-Log 'frontend-err.log'

    # --- 后端 ---
    $backendDir = Join-Path $root 'backend'
    $venvPython = Join-Path $backendDir '.venv\Scripts\python.exe'
    if (-not (Test-Path $venvPython)) { throw "venv 缺失: $venvPython (先运行 python -m venv backend\.venv 并安装依赖)" }

    Write-Host "[1/3] 启动后端 uvicorn :$BACKEND_PORT ..."
    $env:EXTRA_ALLOWED_ORIGINS = "http://localhost:$FRONTEND_PORT,http://127.0.0.1:$FRONTEND_PORT"
    $env:ADMIN_USERS = 'deck'   # 与服务器 docker-compose 保持一致（deck 为管理员）
    $script:backendProc = Start-Process -FilePath $venvPython `
        -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', "$BACKEND_PORT" `
        -WorkingDirectory $backendDir `
        -RedirectStandardOutput (Join-Path $logDir 'backend-out.log') `
        -RedirectStandardError (Join-Path $logDir 'backend-err.log') `
        -WindowStyle Hidden -PassThru
    Write-Host ("    后端 PID = {0}" -f $script:backendProc.Id)

    # 后端一启动就落盘 PID（不等健康检查/前端——中途任何失败都能被 stop-local.ps1 回收）
    @{ backend = $script:backendProc.Id; frontend = $null } | ConvertTo-Json | Set-Content $pidFile

    # --- 等待 API 健康 ---
    Write-Host '[2/3] 等待 API 健康 ...'
    $apiOk = $false
    for ($i = 0; $i -lt 60; $i++) {
        if ($script:backendProc.HasExited) { throw "后端进程启动即退出，查看 logs\backend-err.log" }
        Start-Sleep -Seconds 2
        try {
            $r = Invoke-RestMethod -Uri "http://127.0.0.1:$BACKEND_PORT/api/health" -TimeoutSec 3
            $apiOk = $true; break
        } catch { }
    }
    if (-not $apiOk) {
        Write-Host '    API 未就绪，查看 logs\backend-err.log'
        Get-Content (Join-Path $logDir 'backend-err.log') -Tail 30
        throw '后端启动失败（健康检查超时）'
    }
    Write-Host '    API 就绪'

    # --- 前端 ---
    $frontendDir = Join-Path $root 'frontend'
    if (-not $SkipBuild) {
        Write-Host '[3/3] 构建前端 (tsc + vite build) ...'
        Push-Location $frontendDir
        try { npm run build; if ($LASTEXITCODE -ne 0) { throw '前端构建失败' } } finally { Pop-Location }
    }
    Write-Host "    启动前端 vite preview :$FRONTEND_PORT ..."
    # --strictPort: 端口被占用时直接失败退出，绝不静默漂移到 7461
    $script:frontendProc = Start-Process -FilePath 'cmd.exe' `
        -ArgumentList '/c', "npx vite preview --port $FRONTEND_PORT --host --strictPort" `
        -WorkingDirectory $frontendDir `
        -RedirectStandardOutput (Join-Path $logDir 'frontend-out.log') `
        -RedirectStandardError (Join-Path $logDir 'frontend-err.log') `
        -WindowStyle Hidden -PassThru
    Write-Host ("    前端 PID = {0}" -f $script:frontendProc.Id)

    # --- 更新 PID 文件（补上前端 PID，供 stop-local.ps1 使用） ---
    @{ backend = $script:backendProc.Id; frontend = $script:frontendProc.Id } | ConvertTo-Json |
        Set-Content $pidFile

    Write-Host ''
    Write-Host '=== 家庭医生已启动 ==='
    Write-Host "前端:  http://localhost:$FRONTEND_PORT"
    Write-Host "API:   http://localhost:$BACKEND_PORT"
    Write-Host "文档:  http://localhost:$BACKEND_PORT/docs"
    Write-Host "日志:  $logDir"
} catch {
    Write-Host ''
    Write-Host "[启动失败] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host '正在清理已启动的进程 ...' -ForegroundColor Yellow
    Stop-StartedProcesses
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host '已清理。完整日志见 logs\backend-err.log / logs\frontend-err.log' -ForegroundColor Yellow
    exit 1
}
