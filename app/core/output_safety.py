"""输出文件安全处理：占用检测与自动重命名。"""
import os
from datetime import datetime
from typing import Optional


def is_file_locked(path: str) -> bool:
    """判断文件是否正被其他程序占用（当前进程无法以写方式打开）。

    以 ``r+b`` 尝试打开文件：Excel / WPS 等程序打开文件时会拒绝写共享，
    因此这里会收到 ``PermissionError``；只读文件同样打不开，但会再通过
    ``os.access`` 排除，避免误报成“被占用”。
    """
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r+b"):
            return False
    except PermissionError:
        # 文件被设为只读时同样打不开，但那不属于“被占用”
        return os.access(path, os.W_OK)
    except OSError:
        return True


def build_renamed_path(path: str, now: Optional[datetime] = None) -> str:
    """生成不冲突的新路径：优先追加时间戳，重复时再追加序号。"""
    stem, ext = os.path.splitext(path)
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M")
    candidate = f"{stem}_{stamp}{ext}"
    if not os.path.exists(candidate):
        return candidate

    index = 1
    while True:
        candidate = f"{stem}_{index}{ext}"
        if not os.path.exists(candidate):
            return candidate
        index += 1
