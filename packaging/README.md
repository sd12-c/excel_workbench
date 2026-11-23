# 打包说明（Nuitka）

本目录用于生成 Windows 单文件绿色版。

## 环境要求

- Windows 10 / 11
- Python 3.11（已安装项目依赖）
- Nuitka 4.x
- Visual Studio Build Tools（MSVC）或 MinGW64
- 可选：代码签名证书（对消除 SmartScreen 提示非常重要）

## 一键构建

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_nuitka.ps1
```

脚本会：

1. 把 Nuitka 缓存放到项目内 `.nuitka_cache`，避免系统缓存目录权限问题；
2. 使用 PyQt5 插件、`--onefile` 生成单文件 exe（不把 DLL 散落在 exe 旁边）；
3. 写入图标和版本信息（v1.3.0 / 产品名称 / 公司 / 版权）；
4. 关闭控制台窗口（GUI 程序）；
5. 只把 exe、`使用指南.pdf`、`使用指南.md`、`README.md` 放入 zip；
6. 校验 zip 中不包含源码、`.pyc`、`.git`、测试数据、`config`、`logs`、`out_put` 目录；
7. 可选调用 `signtool` 签名。

## 输出

```text
dist/
├── nuitka/
│   └── ExcelWorkbench.exe          ← 单文件 exe
├── ExcelWorkbench_v1.3.0/           ← 临时组装目录
│   ├── ExcelWorkbench.exe
│   ├── 使用指南.pdf
│   ├── 使用指南.md
│   ├── README.md
│   └── docs/                        ← README 中的界面截图
└── ExcelWorkbench_v1.3.0.zip        ← 最终发布包
```

最终发布包中**只有**：

- `ExcelWorkbench.exe`
- `使用指南.pdf`
- `使用指南.md`
- `README.md`
- `docs/`（README 引用的界面截图）

没有 DLL、源码、测试数据、`config`、`logs`、`out_put`。

## 首次运行

把 exe 放到一个**有写入权限**的目录（例如桌面或 D 盘文件夹），双击运行。程序会自动创建：

```text
ExcelWorkbench.exe
config/
logs/
out_put/
```

- `config/scheme.json`：保存的选项方案；
- `logs/error.log`：错误技术日志；
- `out_put/`：默认输出目录。

如果 exe 放在 Program Files 等无写入权限目录，保存输出和方案时可能失败，建议移动到普通文件夹。

如果双击 exe 没有反应，通常是所在路径含中文、空格或括号；请把整个文件夹移动到 `D:\ExcelWorkbench` 这类纯英文路径后重试。

## 降低 Windows 安全警告

脚本已经做了：

- 写入完整版本信息（文件版本、产品版本、产品名称、公司、版权、文件描述）；
- 设置 exe 图标；
- 关闭控制台窗口；
- 不使用 UPX 等额外压缩壳；
- 单文件模式，不附带 DLL。

但 **SmartScreen / 杀毒软件的“未知发布者”提示，最终必须通过代码签名解决**。脚本预留了签名步骤：

```powershell
$env:CODE_SIGN_PFX = "C:\path\to\cert.pfx"
$env:CODE_SIGN_PASSWORD = "证书密码"
$env:SIGNTOOL_PATH = "C:\Program Files (x86)\Windows Kits\10\bin\...\signtool.exe"

powershell -ExecutionPolicy Bypass -File packaging\build_nuitka.ps1
```

没有证书时，版本信息、图标和规范构建只能降低误报概率，不能完全消除 SmartScreen 提示。

## 修改作者 / 公司 / 版本

编辑 `packaging/build_nuitka.ps1` 顶部的：

```powershell
$Version = "1.3.0"
$ProductName = "Excel 工作台"
$CompanyName = "Excel 工作台 开发团队"
$CopyrightText = "Copyright © 2026 Excel 工作台 开发团队"
```

重新执行脚本即可。

## 关于单文件模式

用户要求最终只交付一个 exe。`--onefile` 会把依赖打在一个 exe 内。运行时 Nuitka 仍会在临时目录解包内部依赖，这是单文件程序的正常机制，退出后会自动清理；exe 所在目录不会出现一堆 DLL。

构建时排除了本工具不需要的 `matplotlib`、`scipy`，减少体积和杀毒软件误报概率。

### QtWebEngine（流水线画布）注意

v1.3 的「流水线画布」使用 `QWebEngineView`，运行依赖：

- `PyQtWebEngine`（已加入 `requirements.txt`）；
- Qt 自带的 `QtWebEngineProcess.exe`、`resources/`、`locales/` 等运行文件。

脚本显式包含 `PyQt5.QtWebEngineWidgets` 和 `PyQt5.QtWebChannel`。如果打包后打开「流水线画布」只显示空白或提示加载失败，请检查 Nuitka 的 PyQt5 插件是否把上述 QtWebEngine 运行文件收进单文件包；可临时改用 `--standalone` 构建对照排查。

## 不打包哪些东西

以下内容仅保留在源码项目中，不会进入发布包：

- `app/` 源码
- `__pycache__` / `*.pyc`
- `.git/`、`.gitignore`
- `测试表格/`
- `config/`、`logs/`、`out_put/`
- `使用指南.md`（与 PDF 内容一致，方便查看/搜索）
- `packaging/` 打包脚本

程序首次运行时会在 exe 旁边自动创建 `config`、`logs`、`out_put`。
