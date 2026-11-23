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

1. 将 Nuitka 缓存重定向至项目内部 `.nuitka_cache`，规避系统缓存目录权限不足问题；
2. Nuitka 使用 `--standalone` + pyqt5 插件，显式包含 `PyQt5.QtWebEngineWidgets`、`PyQt5.QtWebChannel`；
3. 排除 `matplotlib`、`scipy` 等未使用模块，缩减包体积、降低杀毒软件误报；
4. 写入 exe 图标、文件版本、产品版本、产品名称、公司、版权信息；GUI 程序关闭控制台黑窗口；
5. 自动读取本机 PyQt5 Qt 运行库路径，复制 QtWebEngine 必需资源：`QtWebEngineProcess.exe`、`icudtl.dat`、各类 `.pak` 资源包、`qtwebengine_locales` 多语言文件；生成 `qt.conf` 保证 WebEngine 进程可以正确定位资源；
6. 组装发布目录，拷贝程序运行文件 + 文档（`使用指南.pdf` / `使用指南.md` / `README.md`）；
7. 打包为 zip 压缩包；
8. 预留 signtool 代码签名调用环境变量，可配置证书自动签名。

## 输出

```text
dist/
├── nuitka/
│   └── main.dist/                 ← Nuitka原始standalone输出目录
│       ├── ExcelWorkbench.exe
│       ├── libexec/               ← QtWebEngineProcess.exe 存放目录
│       ├── resources/             ← icudtl.dat、*.pak、qtwebengine_locales
│       ├── qt.conf                ← Qt路径配置文件
│       └── 各类依赖dll
├── ExcelWorkbench_v1.3.0/         ← 组装完成的发布目录
│   ├── ExcelWorkbench.exe
│   ├── libexec/
│   ├── resources/
│   ├── qt.conf
│   ├── 使用指南.pdf
│   ├── 使用指南.md
│   └── README.md
└── ExcelWorkbench_v1.3.0.zip     ← 最终对外发布压缩包

```

最终发布 zip 包内包含全部运行依赖：

- `ExcelWorkbench.exe` 主程序
- `libexec/`：QtWebEngine 子进程程序
- `resources/`：WebEngine 网页渲染资源、ICU 字符集、pak 资源包、本地化语言
- `qt.conf`：Qt 资源路径配置文件
- 文档：`使用指南.pdf`、`使用指南.md`、`README.md`

没有 源码、测试数据、`config`、`logs`、`out_put`。

## 首次运行

解压 zip 到本地文件夹，**必须放置在拥有读写权限的纯英文路径，不要放在 Program Files 等受保护系统目录**，示例：`D:\ExcelWorkbench_v1.3.0`。

双击 `ExcelWorkbench.exe` 启动，程序会在 exe 同级目录自动生成 3 个工作目录：
```text
ExcelWorkbench.exe
config/
logs/
out_put/
```

- `config/scheme.json`：保存的选项方案；
- `logs/error.log`：错误技术日志；
- `out_put/`：默认输出目录。

## 常见运行故障
1. 双击程序无响应
- 检查路径：路径不要包含中文、括号、特殊字符，移动到纯英文短路径重试；
- 检查权限：路径必须拥有读写权限，否则无法写入配置文件、日志、输出目录；
2. 流水线画布空白 / 加载失败
- 这是 QtWebEngine 打包最常见问题
- 确认压缩包完整解压，不要直接在 zip 压缩软件内部双击 exe 运行；
- 检查目录中是否存在 `libexec\QtWebEngineProcess.exe`、`resources\icudtl.dat`、`qt.conf`；缺失说明打包阶段复制 WebEngine 资源异常；
- 查看 `logs/error.log`，WebEngine 子进程启动失败日志会记录于此。
3. 打开高级模式闪退
- 这是 QtWebEngine 运行时异常，请检查 `debug.log`。
- `debug.log` 中报错信息通常为`Couldn't mmap icu data file`；
- 找到你的python目录（如果你使用的虚拟环境，请查看虚拟环境目录）
- 进入python目录，找到"Lib\site-packages\PyQt5\Qt5\resources"目录
- 复制其中所有文件
- 粘贴到ExcelWorkbench_v1.3.0.exe同目录下
- 再次运行，即可解决

## 降低 Windows 安全警告

脚本已经做了：

- 写入完整版本信息（文件版本、产品版本、产品名称、公司、版权、文件描述）；
- 设置 exe 图标；
- 关闭控制台窗口；
- 不使用 UPX 等额外压缩壳；

但 **SmartScreen / 杀毒软件的“未知发布者”提示，最终必须通过代码签名解决**。脚本预留了签名步骤：

## 开启自动代码签名
```powershell
$env:CODE_SIGN_PFX = "C:\path\to\cert.pfx"
$env:CODE_SIGN_PASSWORD = "你的pfx证书密码"
$env:SIGNTOOL_PATH = "C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe"
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
- `packaging/` 打包脚本

程序首次运行时会在 exe 旁边自动创建 `config`、`logs`、`out_put`。
