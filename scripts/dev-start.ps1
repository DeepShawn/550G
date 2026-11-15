# 开发启动：在仓库根目录建 .venv（Python 3.11 x64），只在依赖缺失时安装，然后启动桌宠。
# 用法：powershell -ExecutionPolicy Bypass -File scripts\dev-start.ps1 [-- 额外参数]
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Py)) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        Write-Error "未找到 Python 启动器 py。请安装 Python 3.11 x64：https://www.python.org/downloads/windows/"
    }
    & py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Error "创建虚拟环境失败（需要 Python 3.11 x64）。" }
}

& $Py -c "import PySide6" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "安装依赖…"
    & $Py -m pip install --disable-pip-version-check -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { Write-Error "依赖安装失败，请检查网络后重试。" }
}

& $Py main.py @args
exit $LASTEXITCODE
