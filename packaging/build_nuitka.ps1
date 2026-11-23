# Excel 工作台 · Nuitka 打包脚本（Qt5 PyQt5 WebEngine专用）
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
Set-Location $Root

$Version = "1.3.0"
$ProductName = "Excel 工作台"
$CompanyName = "Excel 工作台 开发团队"
$CopyrightText = "Copyright © 2026 Excel 工作台 开发团队"
$ExeName = "ExcelWorkbench.exe"

$IconPath = Join-Path $Root "app\resources\app.ico"
$GuidePdf = Join-Path $Root "使用指南.pdf"
$GuideMd = Join-Path $Root "使用指南.md"
$ReadmeMd = Join-Path $Root "README.md"

$OutputDir = Join-Path $Root "dist\nuitka"
$NuitkaDistDir = Join-Path $OutputDir "main.dist"
$StageDir = Join-Path $Root "dist\ExcelWorkbench_v$Version"
$ZipFile = Join-Path $Root "dist\ExcelWorkbench_v$Version.zip"
$CacheDir = Join-Path $Root ".nuitka_cache"

# ========== 自动读取Qt路径 ==========
$qtInfo = python -c "
from PyQt5.QtCore import QLibraryInfo
print(QLibraryInfo.location(QLibraryInfo.LibraryExecutablesPath))
print(QLibraryInfo.location(QLibraryInfo.DataPath))
"
$qtBinPath = $qtInfo[0]
$qtDataPath = $qtInfo[1]

$IcuSrc = Join-Path $qtDataPath "resources\icudtl.dat"
$WebEngineProcessSrc = Join-Path $qtBinPath "QtWebEngineProcess.exe"
$PakSrc = Join-Path $qtDataPath "resources\qtwebengine_resources.pak"
$Pak100Src = Join-Path $qtDataPath "resources\qtwebengine_resources_100p.pak"
$Pak200Src = Join-Path $qtDataPath "resources\qtwebengine_resources_200p.pak"
$DevToolsPakSrc = Join-Path $qtDataPath "resources\qtwebengine_devtools_resources.pak"
$LocalesSrc = Join-Path $qtDataPath "qtwebengine_locales"

# 前置校验（Qt5只校验这两个核心文件）
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "未找到python命令" }
if (-not (Test-Path $IconPath)) { throw "图标不存在：$IconPath" }
if (-not (Test-Path $IcuSrc)) { throw "找不到 icudtl.dat：$IcuSrc" }
if (-not (Test-Path $WebEngineProcessSrc)) { throw "找不到 QtWebEngineProcess.exe：$WebEngineProcessSrc" }

$env:NUITKA_CACHE_DIR = $CacheDir
$env:CL = "/utf-8"
$env:VSLANG = "1033"

# ========== 清理旧产物 ==========
Write-Host "==> 清理旧构建文件" -ForegroundColor Cyan
if (Test-Path $OutputDir) { Remove-Item $OutputDir -Recurse -Force }
if (Test-Path $StageDir) { Remove-Item $StageDir -Recurse -Force }
if (Test-Path $ZipFile) { Remove-Item $ZipFile -Force }
New-Item -ItemType Directory -Force $OutputDir | Out-Null

# ========== Nuitka打包 ==========
Write-Host "==> 开始 Nuitka Standalone 打包（PyQt5 WebEngine Qt5）" -ForegroundColor Cyan
$nuitkaArgs = @(
    "-m", "nuitka",
    "--standalone",
    "--enable-plugin=pyqt5",
    "--include-qt-plugins=sensible",
    "--include-module=PyQt5.QtWebEngineWidgets",
    "--include-module=PyQt5.QtWebChannel",
    "--include-data-dir=app/resources=app/resources",
    "--nofollow-import-to=matplotlib",
    "--nofollow-import-to=scipy",
    "--noinclude-pytest-mode=nofollow",
    "--noinclude-unittest-mode=nofollow",
    "--windows-console-mode=disable",
    "--windows-icon-from-ico=$IconPath",
    "--company-name=$CompanyName",
    "--product-name=$ProductName",
    "--product-version=$Version",
    "--file-version=$Version.0",
    "--copyright=$CopyrightText",
    "--output-dir=$OutputDir",
    "--output-filename=$ExeName",
    "--remove-output",
    "--assume-yes-for-downloads",
    "main.py"
)
& python $nuitkaArgs
if ($LASTEXITCODE -ne 0) { throw "Nuitka打包失败，退出码 $LASTEXITCODE" }

$ExeFullPath = Join-Path $NuitkaDistDir $ExeName
if (-not (Test-Path $ExeFullPath)) { throw "打包完成，但找不到exe：$ExeFullPath" }

# ========== 部署Qt5 WebEngine资源（重点：Qt5不需要v8快照） ==========
Write-Host "==> 部署QtWebEngine资源" -ForegroundColor Cyan
$libexecDir = Join-Path $NuitkaDistDir "libexec"
$resDir = Join-Path $NuitkaDistDir "resources"
New-Item -ItemType Directory -Force $libexecDir | Out-Null
New-Item -ItemType Directory -Force $resDir | Out-Null

# qt.conf（主程序读取）
$qtConfContent = @'
[Paths]
Prefix = .
LibExecPath = libexec
ResourcesPath = resources
'@
$qtConfFile = Join-Path $NuitkaDistDir "qt.conf"
$qtConfContent | Out-File $qtConfFile -Encoding utf8

# 复制Qt5必需资源
Copy-Item $WebEngineProcessSrc (Join-Path $libexecDir "QtWebEngineProcess.exe") -Force
Copy-Item $IcuSrc (Join-Path $resDir "icudtl.dat") -Force
Copy-Item $PakSrc (Join-Path $resDir "qtwebengine_resources.pak") -Force
if (Test-Path $Pak100Src) { Copy-Item $Pak100Src (Join-Path $resDir "qtwebengine_resources_100p.pak") -Force }
if (Test-Path $Pak200Src) { Copy-Item $Pak200Src (Join-Path $resDir "qtwebengine_resources_200p.pak") -Force }
if (Test-Path $DevToolsPakSrc) { Copy-Item $DevToolsPakSrc (Join-Path $resDir "qtwebengine_devtools_resources.pak") -Force }
if (Test-Path $LocalesSrc) {
    Copy-Item $LocalesSrc (Join-Path $resDir "qtwebengine_locales") -Recurse -Force
}

# ========== 组装发布包 ==========
Write-Host "==> 组装发布包目录" -ForegroundColor Cyan
New-Item -ItemType Directory -Force $StageDir | Out-Null
Copy-Item (Join-Path $NuitkaDistDir "*") $StageDir -Recurse -Force

# 按需复制文档，不需要就注释
if (Test-Path $GuidePdf) { Copy-Item $GuidePdf $StageDir -Force }
if (Test-Path $GuideMd) { Copy-Item $GuideMd $StageDir -Force }
if (Test-Path $ReadmeMd) { Copy-Item $ReadmeMd $StageDir -Force }

# ========== 压缩：压缩包根目录直接是exe ==========
Write-Host "==> 生成压缩包 $ZipFile" -ForegroundColor Cyan
Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipFile -Force

# ========== 输出信息 ==========
$exeInfo = (Get-Item $ExeFullPath)
Write-Host "`n==> 构建完成" -ForegroundColor Green
Write-Host "EXE : $ExeFullPath"
Write-Host "ZIP : $ZipFile"
Write-Host "大小: $([math]::Round($exeInfo.Length / 1MB, 1)) MB"
Write-Host "版本: $Version.0"
Write-Host "产品: $ProductName"
Write-Host "公司: $CompanyName"
Write-Host "版权: $CopyrightText`n"
