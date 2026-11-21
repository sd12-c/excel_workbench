"""统一异常处理：把底层异常翻译成面向用户的中文提示。

设计原则：

1. 运行日志面板只展示“发生了什么 + 该怎么处理”，不再输出原始 Traceback；
2. 完整 Traceback 仍会静默写入 ``logs/error.log``，方便开发者排查；
3. 业务层可主动抛出 :class:`FriendlyError`，携带已经写好的中文提示。
"""
import errno
import os
import re
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import List

from app.config import ERROR_LOG_FILE, LOG_DIR

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_MODULE_RE = re.compile(r"No module named ['\"]([^'\"]+)['\"]")
_MAX_TEXT = 300
_MAX_LOG_SIZE = 1024 * 1024  # 错误日志超过 1MB 自动滚动一次


class FriendlyError(Exception):
    """业务层主动抛出的异常，message 会原样展示给用户。"""

    def __init__(self, message: str, *, detail: str = "", hint: str = "") -> None:
        super().__init__(message)
        self.title = str(message)
        self.detail = detail
        self.hint = hint


@dataclass(frozen=True)
class FriendlyErrorInfo:
    """一条可直接展示在运行日志中的错误说明。"""

    title: str
    detail: str = ""
    hint: str = ""

    def to_lines(self) -> List[str]:
        lines = [self.title]
        if self.detail:
            lines.append(f"原因：{self.detail}")
        if self.hint:
            lines.append(f"建议：{self.hint}")
        return lines

    def to_text(self) -> str:
        return "\n".join(self.to_lines())


# --------------------------------------------------------------------------- #
# 对外接口
# --------------------------------------------------------------------------- #
def explain(exc: BaseException) -> FriendlyErrorInfo:
    """把任意异常翻译成友好的中文提示（不含 Traceback）。"""
    if isinstance(exc, FriendlyError):
        return FriendlyErrorInfo(
            _clean(exc.title) or "操作失败",
            _clean(exc.detail),
            _clean(exc.hint),
        )

    message = _clean(exc) if str(exc).strip() else ""
    filename = _name_of(exc)
    winerror = getattr(exc, "winerror", None)
    code = getattr(exc, "errno", None)
    type_name = type(exc).__name__

    # ---- 文件与权限 -------------------------------------------------------
    if isinstance(exc, PermissionError):
        if _is_directory(getattr(exc, "filename", None)):
            return FriendlyErrorInfo(
                "目标路径是文件夹",
                f"{_quoted(filename, '目标路径')}是一个文件夹，不能直接当作文件写入。",
                "请填写完整的文件名（例如 结果.xlsx），或改选其他保存位置后重试。",
            )
        if _looks_like_file_in_use(message, winerror):
            return FriendlyErrorInfo(
                "文件被占用，暂时无法写入",
                f"{_quoted(filename, '目标文件')}正被 Excel、WPS 或其他程序打开。",
                "请关闭该文件后重试；也可以把输出位置改到其他文件夹。",
            )
        return FriendlyErrorInfo(
            "没有权限读写文件",
            f"当前用户无法访问{_quoted(filename, '该文件')}，文件可能被设为只读。",
            "请检查文件或文件夹的只读属性，或把文件复制到桌面等可写位置后重试。",
        )

    if isinstance(exc, FileNotFoundError):
        if winerror == 206:
            return FriendlyErrorInfo(
                "文件路径太长",
                "文件所在的路径层级过多或文件名过长，Windows 无法访问。",
                "请把文件或输出目录移动到层级更浅的位置（例如 D:\\导出）后重试。",
            )
        return FriendlyErrorInfo(
            "找不到文件",
            f"{_quoted(filename, '目标文件')}不存在，可能已被移动、重命名或删除。",
            "请重新添加文件后再运行；如果文件在网盘或移动硬盘上，请先保存到本地。",
        )

    if isinstance(exc, IsADirectoryError):
        return FriendlyErrorInfo(
            "选择的是文件夹，不是文件",
            f"{_quoted(filename, '该路径')}是一个文件夹，无法当作文件读写。",
            "保存结果时请填写完整文件名（例如 结果.xlsx），不要只选文件夹。",
        )

    if isinstance(exc, NotADirectoryError):
        return FriendlyErrorInfo(
            "路径中包含不存在的文件夹",
            f"无法访问{_quoted(filename, '目标路径')}，上级目录可能已被删除。",
            "请重新选择输出位置，或先手动创建对应的文件夹。",
        )

    if isinstance(exc, FileExistsError):
        return FriendlyErrorInfo(
            "目标文件已存在",
            "同名文件已存在，且当前无法自动改名。",
            "请手动删除或重命名同名文件后重试。",
        )

    if isinstance(exc, UnicodeDecodeError):
        encoding = getattr(exc, "encoding", "") or "未知"
        return FriendlyErrorInfo(
            "文件编码无法识别",
            f"按 {encoding} 解码时遇到无法识别的字符。",
            "请用记事本或 Excel 将文件另存为 UTF-8 或 GBK 编码后重试。",
        )

    if isinstance(exc, UnicodeEncodeError):
        return FriendlyErrorInfo(
            "内容包含无法保存的字符",
            "部分特殊字符无法用当前编码写入。",
            "请删除表情符号等特殊字符，或改用 UTF-8 编码保存后重试。",
        )

    if isinstance(exc, MemoryError):
        return FriendlyErrorInfo(
            "内存不足",
            "待处理的数据量超过了当前可用内存。",
            "请关闭其他占用内存的程序，或分批次处理更少的文件。",
        )

    # ---- 依赖组件 ---------------------------------------------------------
    if isinstance(exc, ImportError):
        module = getattr(exc, "name", None) or _module_from_message(message)
        if module in {"xlrd", "xlwt"}:
            return FriendlyErrorInfo(
                "缺少读写 .xls 旧格式的组件",
                f"当前环境没有安装 {module}。",
                f"请运行 pip install {module}，或把文件另存为 .xlsx 格式后重试。",
            )
        return FriendlyErrorInfo(
            "缺少运行所需的组件",
            f"缺少模块：{module}。" if module else (message or "导入组件时失败。"),
            "请运行 pip install -r requirements.txt 安装依赖后重新启动程序。",
        )

    if type_name == "BadZipFile":
        return FriendlyErrorInfo(
            "文件已损坏或不是有效的 Excel 文件",
            "文件内容不是标准的 xlsx 压缩包结构。",
            "请先用 Excel 打开确认文件能正常显示；若是 .xls 旧格式，请另存为 .xlsx 后重试。",
        )

    if type_name == "InvalidFileException":
        return FriendlyErrorInfo(
            "无法识别该文件的格式",
            "文件不符合 Excel 标准格式，可能已损坏或只是修改了扩展名。",
            "请用 Excel 打开并另存为 .xlsx 后再试。",
        )

    if type_name == "EmptyDataError":
        return FriendlyErrorInfo(
            "文件里没有可读取的数据",
            "文件内容为空，或只有空行。",
            "请确认文件不是空表，并删除表头前的空行后重试。",
        )

    if type_name == "ParserError":
        return FriendlyErrorInfo(
            "文件格式无法解析",
            message or "文本结构不符合预期。",
            "请确认文件扩展名与真实格式一致（例如把 CSV 直接改名为 .xlsx 会导致此错误）。",
        )

    if type_name == "XLRDError":
        return FriendlyErrorInfo(
            "无法读取该 Excel 文件",
            message or "文件可能是新版 .xlsx，却使用了旧版读取组件。",
            "请把文件另存为 .xlsx 后重试。",
        )

    # ---- 数据与参数 -------------------------------------------------------
    if isinstance(exc, KeyError):
        key = exc.args[0] if exc.args else ""
        return FriendlyErrorInfo(
            "找不到指定的列或工作表",
            f"文件中缺少「{key}」。" if key else "文件中缺少需要的内容。",
            "请核对列名 / 工作表名是否与文件中的完全一致（注意多余空格和全角半角）。",
        )

    if isinstance(exc, IndexError):
        return FriendlyErrorInfo(
            "读取到的数据不完整",
            "文件可能为空表，或缺少表头 / 数据行。",
            "请用 Excel 打开确认内容完整后重试。",
        )

    if isinstance(exc, ValueError):
        special = _special_value_error(message)
        if special is not None:
            return special
        if _has_chinese(message):
            return FriendlyErrorInfo(message)
        return FriendlyErrorInfo(
            "数据内容不符合要求",
            message or "传入的参数或文件内容格式不正确。",
            "请检查填写的选项和文件内容后重试。",
        )

    if isinstance(exc, TypeError):
        return FriendlyErrorInfo(
            "数据类型不匹配",
            message or "程序无法按预期处理该数据类型。",
            "请确认表格中没有混入图片、公式错误值等特殊内容后重试。",
        )

    # ---- 系统调用 ---------------------------------------------------------
    if isinstance(exc, RecursionError):
        return FriendlyErrorInfo(
            "数据层级过深，无法继续处理",
            "处理过程中嵌套层级超出上限。",
            "请尝试拆分文件，或减少一次性处理的数据量后重试。",
        )

    if isinstance(exc, OSError):
        title, hint = _os_error_hint(code, winerror, message)
        return FriendlyErrorInfo(
            title,
            message or getattr(exc, "strerror", "") or "读写文件时发生错误。",
            hint,
        )

    if isinstance(exc, RuntimeError) and _has_chinese(message):
        return FriendlyErrorInfo(message)

    # ---- 兜底 -------------------------------------------------------------
    if _has_chinese(message):
        return FriendlyErrorInfo(message)
    detail = f"{type_name}：{message}" if message else f"错误类型：{type_name}。"
    return FriendlyErrorInfo(
        "程序遇到未预期的问题",
        detail,
        "请重试一次；如果反复出现，请把项目目录下 logs/error.log 的内容提供给开发者。",
    )


def friendly_text(exc: BaseException) -> str:
    """返回可直接写入日志面板的友好提示文本。"""
    return explain(exc).to_text()


def record_exception(exc: BaseException, context: str = "") -> None:
    """把完整 Traceback 静默写入 logs/error.log（不展示在界面上）。"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        _rotate_log()
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as fp:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            fp.write(f"\n[{stamp}] {context or '未标注场景'}\n")
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=fp)
    except Exception:  # noqa: BLE001 - 日志落盘失败也不能影响主流程
        pass


# --------------------------------------------------------------------------- #
# 内部工具
# --------------------------------------------------------------------------- #
def _rotate_log() -> None:
    """错误日志超过上限时保留一份历史文件，避免无限增大。"""
    try:
        if os.path.getsize(ERROR_LOG_FILE) < _MAX_LOG_SIZE:
            return
        os.replace(ERROR_LOG_FILE, ERROR_LOG_FILE + ".1")
    except OSError:
        pass


def _clean(value) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > _MAX_TEXT:
        text = text[:_MAX_TEXT] + "……"
    return text


def _has_chinese(text: str) -> bool:
    return bool(text and _CJK_RE.search(str(text)))


def _name_of(exc: BaseException) -> str:
    filename = getattr(exc, "filename", None)
    if not filename:
        return ""
    return os.path.basename(str(filename).rstrip("\\/")) or str(filename)


def _quoted(filename: str, fallback: str) -> str:
    return f"「{filename}」" if filename else fallback


def _is_directory(path) -> bool:
    if not path:
        return False
    try:
        return os.path.isdir(str(path))
    except (OSError, ValueError):
        return False


def _looks_like_file_in_use(message: str, winerror) -> bool:
    if winerror == 32:
        return True
    text = (message or "").lower()
    return any(marker in text for marker in (
        "being used", "used by another process", "另一个程序", "正被", "占用",
    ))


def _module_from_message(message: str) -> str:
    match = _MODULE_RE.search(message or "")
    return match.group(1) if match else ""


def _special_value_error(message: str):
    text = (message or "").lower()
    if "excel file format" in text or "format cannot be determined" in text:
        return FriendlyErrorInfo(
            "无法识别文件格式",
            "文件内容与 Excel 格式不匹配，可能只是修改了扩展名。",
            "请用 Excel 打开并另存为 .xlsx 后再试。",
        )
    if "worksheet named" in text or "no sheet named" in text:
        return FriendlyErrorInfo(
            "找不到指定的工作表",
            message,
            "请核对工作表名称是否与文件中的完全一致（注意空格和全角半角）。",
        )
    return None


def _os_error_hint(code, winerror, message: str):
    if code == errno.ENOSPC or winerror == 112:
        return ("磁盘空间不足",
                "请清理磁盘空间，或把输出位置改到其他磁盘后重试。")
    if code == errno.ENAMETOOLONG or winerror == 206:
        return ("文件路径太长",
                "请把输出目录换到层级更浅的位置（例如 D:\\导出）后重试。")
    if _looks_like_file_in_use(message, winerror):
        return ("文件被占用，暂时无法写入",
                "请关闭正在使用该文件的 Excel / WPS 后重试。")
    if code == errno.EACCES or winerror == 5:
        return ("没有权限读写文件",
                "请检查文件或文件夹的只读属性，或换一个可写的目录。")
    if code == errno.ENOENT or winerror == 3:
        return ("找不到文件或文件夹",
                "请确认路径是否存在，必要时重新选择文件或输出位置。")
    return ("文件读写失败",
            "请检查文件是否损坏、路径是否有效，并确认磁盘空间充足。")
