# Excel 工作台 · Nuitka 打包脚本
# 用法：powershell -ExecutionPolicy Bypass -File packaging\build_nuitka.ps1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Version = "1.3.0"
$ProductName = "Excel 工作台"
$CompanyName = "Excel 工作台 开发团队"
$CopyrightText = "Copyright © 2026 Excel 工作台 开发团队"
$ExeName = "ExcelWorkbench.exe"

$IconPath = Join-Path $Root "app\resources\app.ico"
$GuidePath = Join-Path $Root "使用指南.pdf"
$GuideMdPath = Join-Path $Root "使用指南.md"
$ReadmePath = Join-Path $Root "README.md"
$OutputDir = Join-Path $Root "dist\nuitka"
$StageDir = Join-Path $Root "dist\ExcelWorkbench_v$Version"
$ZipPath = Join-Path $Root "dist\ExcelWorkbench_v$Version.zip"
$CacheDir = Join-Path $Root ".nuitka_cache"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "没有找到 python，请先安装 Python 并加入 PATH。"
}
if (-not (Test-Path $IconPath)) {
    throw "缺少图标文件：$IconPath"
}
if (-not (Test-Path $GuidePath)) {
    throw "缺少使用指南：$GuidePath"
}

# Nuitka 默认缓存目录在当前环境可能不可写，改用项目内缓存
$env:NUITKA_CACHE_DIR = $CacheDir
# 源码/版本资源含中文，强制 MSVC 按 UTF-8 读取，避免代码页 936 报错
$env:CL = "/utf-8"
$env:VSLANG = "1033"
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null

Write-Host "==> 清理旧构建..." -ForegroundColor Cyan
Remove-Item $OutputDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $StageDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Write-Host "==> 开始 Nuitka 单文件构建..." -ForegroundColor Cyan
$nuitkaArgs = @(
    "-m", "nuitka",
    "--onefile",
    "--enable-plugin=pyqt5",
    "--include-module=PyQt5.QtWebEngineWidgets",
    "--include-module=PyQt5.QtWebChannel",
    "--include-data-dir=app/resources=app/resources",
    "--nofollow-import-to=matplotlib",
    "--nofollow-import-to=scipy",
    "--noinclude-pytest-mode=nofollow",
    "--noinclude-unittest-mode=nofollow",
    "--noinclude-pydoc-mode=nofollow",
    "--windows-console-mode=disable",
    "--windows-icon-from-ico=$IconPath",
    "--company-name=$CompanyName",
    "--product-name=$ProductName",
    "--file-version=$Version.0",
    "--product-version=$Version.0",
    "--file-description=$ProductName",
    "--copyright=$CopyrightText",
    "--output-dir=$OutputDir",
    "--output-filename=$ExeName",
    "--remove-output",
    "--assume-yes-for-downloads",
    "main.py"
)
& python @nuitkaArgs
if ($LASTEXITCODE -ne 0) {
    throw "Nuitka 构建失败，退出码：$LASTEXITCODE"
}

$ExePath = Join-Path $OutputDir $ExeName
if (-not (Test-Path $ExePath)) {
    throw "构建结束但没有找到 exe：$ExePath"
}

# 可选：使用代码签名证书降低 SmartScreen / 杀毒软件误报。
# 设置 CODE_SIGN_PFX（.pfx 路径）、CODE_SIGN_PASSWORD，并确保 signtool 在 PATH，
# 或设置 SIGNTOOL_PATH 指向 signtool.exe。
if ($env:CODE_SIGN_PFX) {
    $signTool = $env:SIGNTOOL_PATH
    if (-not $signTool) {
        $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
        if ($command) { $signTool = $command.Source }
    }
    if (-not $signTool) {
        Write-Warning "设置了 CODE_SIGN_PFX，但没有找到 signtool.exe，跳过签名。"
    } else {
        Write-Host "==> 正在签名..." -ForegroundColor Cyan
        & $signTool sign /fd SHA256 /f $env:CODE_SIGN_PFX /p $env:CODE_SIGN_PASSWORD `
            /tr http://timestamp.digicert.com /td SHA256 $ExePath
        if ($LASTEXITCODE -ne 0) {
            throw "代码签名失败，退出码：$LASTEXITCODE"
        }
    }
}

Write-Host "==> 组装压缩包（只放 exe 和说明文档）..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
Copy-Item -LiteralPath $ExePath -Destination (Join-Path $StageDir $ExeName)
Copy-Item -LiteralPath $GuidePath -Destination $StageDir
Copy-Item -LiteralPath $GuideMdPath -Destination $StageDir
Copy-Item -LiteralPath $ReadmePath -Destination $StageDir
$DocsDir = Join-Path $Root "docs"
if (Test-Path $DocsDir) {
    Copy-Item -LiteralPath $DocsDir -Destination $StageDir -Recurse
}

Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -Force

# 校验压缩包内容，确保没有源码、缓存、测试数据和运行目录
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
try {
    $entries = @($archive.Entries | ForEach-Object { $_.FullName })
} finally {
    $archive.Dispose()
}
$forbidden = $entries | Where-Object {
    $_ -match '(^|/)(config|logs|out_put|测试表格|app)(/|$)' -or
    $_ -match '\.(py|pyc|pyo|pyd|git|gitignore)$' -or
    $_ -match '(^|/)\.git(/|$)'
}
if ($forbidden) {
    throw "压缩包中出现不应包含的内容：`n$($forbidden -join "`n")"
}

$exeCount = @(Get-ChildItem -LiteralPath $StageDir -Filter *.exe).Count
$dllCount = @(Get-ChildItem -LiteralPath $StageDir -Filter *.dll -Recurse).Count
if ($exeCount -ne 1 -or $dllCount -ne 0) {
    throw "产物不是单文件：exe=$exeCount, dll=$dllCount"
}

$info = (Get-Item -LiteralPath $ExePath).VersionInfo
Write-Host ""
Write-Host "==> 构建完成" -ForegroundColor Green
Write-Host "EXE : $ExePath"
Write-Host "ZIP : $ZipPath"
Write-Host "大小: $([math]::Round((Get-Item $ExePath).Length / 1MB, 1)) MB"
Write-Host "版本: $($info.FileVersion)"
Write-Host "产品: $($info.ProductName)"
Write-Host "公司: $($info.CompanyName)"
Write-Host "版权: $($info.LegalCopyright)"
Write-Host "压缩包内容:"
$entries | ForEach-Object { Write-Host "  - $_" }
