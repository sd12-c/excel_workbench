"""全局配置与样式表加载。"""
import os
import sys

APP_NAME = "Excel 批量工作台"
APP_VERSION = "1.1.1"
APP_SUBTITLE = "Batch Processing Studio"

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))

# 项目根目录：开发时是 app 的上一级；打包后是 exe 所在目录。
# 输出目录、日志、方案文件都放在这个目录下，方便绿色版随身携带。
_IS_FROZEN = bool(getattr(sys, "frozen", False) or "__compiled__" in globals())
if _IS_FROZEN:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(sys.argv[0]))
else:
    PROJECT_ROOT = os.path.dirname(_PKG_DIR)

RESOURCE_DIR = os.path.join(_PKG_DIR, "resources")
STYLE_FILE = os.path.join(RESOURCE_DIR, "styles.qss")
APP_ICON_FILE = os.path.join(RESOURCE_DIR, "app.ico")

# 默认输出根目录：<项目根>/out_put
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "out_put")

# 错误日志目录（仅保存技术细节，界面上只显示友好提示）
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
ERROR_LOG_FILE = os.path.join(LOG_DIR, "error.log")


# 保存方案（输出路径 / 勾选参数）的默认配置文件：<项目根>/config/scheme.json
SCHEME_DIR = os.path.join(PROJECT_ROOT, "config")
SCHEME_FILE = os.path.join(SCHEME_DIR, "scheme.json")

SUPPORTED_EXCEL = (".xlsx", ".xls", ".xlsm")
SUPPORTED_CSV = (".csv",)


def ensure_output_dir() -> str:
    """确保默认输出目录存在，返回其绝对路径。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return OUTPUT_DIR


def ensure_runtime_dirs() -> None:
    """首次运行时自动创建 config、logs、out_put 目录。"""
    for directory in (OUTPUT_DIR, LOG_DIR, SCHEME_DIR):
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError:
            # 目录不可写时仍然允许启动，具体错误会在保存时提示
            pass


def load_stylesheet() -> str:
    """读取 QSS 并把 @RES@ 占位符替换成资源目录绝对路径。"""
    try:
        with open(STYLE_FILE, "r", encoding="utf-8") as fp:
            qss = fp.read()
    except OSError:
        return ""
    res = RESOURCE_DIR.replace("\\", "/")
    return qss.replace("@RES@", res)