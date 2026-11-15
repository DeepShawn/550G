# Windows 发布构建：干净虚拟环境 → 测试 → 素材校验 → PyInstaller onedir → 冻结包冒烟自检 → ZIP + SHA-256。
# 用法（仓库根目录）：powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1 [-Release]
#   -Release  正式发布：素材仍是占位（pets.json placeholder=true）时失败。
param([switch]$Release, [string]$Python = "py -3.11")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Run($exe, [string[]]$a) {
    & $exe @a
    if ($LASTEXITCODE -ne 0) { throw "命令失败（$LASTEXITCODE）：$exe $($a -join ' ')" }
}

$Version = (Select-String -Path app\version.py -Pattern 'APP_VERSION = "(.+)"').Matches[0].Groups[1].Value
$Stage = (Select-String -Path app\version.py -Pattern 'APP_STAGE = "(.*)"').Matches[0].Groups[1].Value
if (-not (Select-String -Path packaging\version_info.txt -Pattern "'FileVersion', '$Version'" -Quiet)) {
    throw "packaging\version_info.txt 的 FileVersion 与 app\version.py ($Version) 不一致"
}
$Tag = if ($Stage) { "v$Version-$Stage" } else { "v$Version" }
$Name = "550G_GPT_DesktopPets_${Tag}_win_x64"
Write-Host "构建 $Name"

# 1. 干净构建环境
$Venv = Join-Path $Root ".venv-build"
if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
Invoke-Expression "$Python -m venv `"$Venv`""
$Py = Join-Path $Venv "Scripts\python.exe"
Run $Py @("-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements-build.txt")
Run $Py @("-c", "import struct,sys; assert struct.calcsize('P')==8, 'need x64 Python'; print(sys.version)")

# 2. 测试与素材校验
$env:QT_QPA_PLATFORM = "offscreen"
Run $Py @("-m", "pytest", "-q")
$va = @("tools\validate_assets.py")
if ($Release) { $va += "--release" }
Run $Py $va
Remove-Item Env:QT_QPA_PLATFORM

# 3. PyInstaller
foreach ($d in "build", "dist") { if (Test-Path $d) { Remove-Item -Recurse -Force $d } }
Run $Py @("-m", "PyInstaller", "--noconfirm", "--clean", "packaging\windows.spec")
$Dist = Join-Path $Root "dist\DesktopPets550G"
$Exe = Join-Path $Dist "DesktopPets550G.exe"
if (-not (Test-Path $Exe)) { throw "未生成 $Exe" }

# 4. 冻结包冒烟自检（从其他工作目录启动，验证资源路径与 cwd 无关）
$Smoke = Join-Path $env:TEMP "pets550g-smoke-$PID.json"
Push-Location $env:TEMP
try {
    $p = Start-Process -FilePath $Exe -ArgumentList @("--smoke-test", "`"$Smoke`"", "--smoke-seconds", "4") -Wait -PassThru
} finally { Pop-Location }
if ($p.ExitCode -ne 0 -or -not (Test-Path $Smoke)) { throw "冻结包自检失败，退出码 $($p.ExitCode)" }
Get-Content $Smoke -Encoding UTF8 | Write-Host

# 5. 组装发布目录
$Release_Dir = Join-Path $Root "release\$Name"
if (Test-Path (Join-Path $Root "release")) { Remove-Item -Recurse -Force (Join-Path $Root "release") }
New-Item -ItemType Directory -Force $Release_Dir | Out-Null
Copy-Item -Recurse "$Dist\*" $Release_Dir
Copy-Item docs\使用说明.txt, CHANGELOG.md, THIRD_PARTY_NOTICES.txt, docs\已知限制与测试记录.md $Release_Dir
Copy-Item $Smoke (Join-Path $Release_Dir "build_smoke_report.json")
& $Py -m pip freeze --all | Out-File -Encoding utf8 (Join-Path $Release_Dir "build_environment.txt")
"Windows: $([Environment]::OSVersion.VersionString)" | Out-File -Append -Encoding utf8 (Join-Path $Release_Dir "build_environment.txt")

# 6. ZIP + SHA-256（源码包另行用 git archive 生成）
$Zip = Join-Path $Root "release\$Name.zip"
Compress-Archive -Path $Release_Dir -DestinationPath $Zip -Force
$Hash = (Get-FileHash -Algorithm SHA256 $Zip).Hash.ToLower()
"$Hash  $Name.zip" | Out-File -Encoding ascii (Join-Path $Root "release\SHA256SUMS.txt")
git archive --format=zip --prefix="550G_GPT_DesktopPets_${Tag}_source/" -o "release\550G_GPT_DesktopPets_${Tag}_source.zip" HEAD 2>$null
if ($LASTEXITCODE -eq 0) {
    $SH = (Get-FileHash -Algorithm SHA256 "release\550G_GPT_DesktopPets_${Tag}_source.zip").Hash.ToLower()
    "$SH  550G_GPT_DesktopPets_${Tag}_source.zip" | Out-File -Append -Encoding ascii (Join-Path $Root "release\SHA256SUMS.txt")
}
Get-Content (Join-Path $Root "release\SHA256SUMS.txt")
Write-Host "完成：$Zip"
Write-Host "注意：构建与自检通过 ≠ 实机验收。请按 docs\handoff\05_Windows验收清单.md 在无 Python 的机器上逐项测试。"
