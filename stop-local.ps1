# 家庭医生 · 本地服务停止脚本
# 用法: powershell -ExecutionPolicy Bypass -File stop-local.ps1
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$pidFile = Join-Path $root 'logs\service-pids.json'

# 优雅停止：先发 WM_CLOSE（taskkill 不带 /F），等待最多 2 秒让进程自行收尾（uvicorn 完成 in-flight 请求/关闭 DB 句柄），仍存活再强杀
function Stop-ServiceTree {
    param([int]$ProcId, [string]$Name)
    if (-not (Get-Process -Id $ProcId -ErrorAction SilentlyContinue)) { return }

    # 1) 优雅：发 WM_CLOSE（对无消息循环的控制台进程可能无效，属预期）
    & taskkill.exe /PID $ProcId 2>$null | Out-Null
    $deadline = (Get-Date).AddSeconds(2)
    while ((Get-Date) -lt $deadline -and (Get-Process -Id $ProcId -ErrorAction SilentlyContinue)) {
        Start-Sleep -Milliseconds 200
    }

    # 2) 兜底：仍存活 → 连同子进程一起强杀（前端是 cmd.exe 壳，需连带 node 子进程）
    if (Get-Process -Id $ProcId -ErrorAction SilentlyContinue) {
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcId" -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Stop-Process -Id $ProcId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "已停止 $name (PID $procId)"
}

if (Test-Path $pidFile) {
    $pids = Get-Content $pidFile -Raw | ConvertFrom-Json
    foreach ($name in 'backend', 'frontend') {
        $procId = $pids.$name
        if ($procId) {
            Stop-ServiceTree -ProcId $procId -Name $name
        }
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
} else {
    Write-Host '未找到 logs\service-pids.json，按端口清理 7459/7460 ...'
}

# 兜底: 无论 pidFile 是否命中，一律清理端口（防止死 PID 记录让旧实例成为孤儿）
foreach ($port in 7459, 7460) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conns) {
        $conns | Select-Object -ExpandProperty OwningProcess -Unique |
            ForEach-Object {
                if ($_ -ne $PID) { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
            }
        Write-Host "已清理端口 $port"
    }
}

# 清理可能残留的 node vite preview / python uvicorn
Get-Process node -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path -like '*homedoctor*' } |
    ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Write-Host '完成'
