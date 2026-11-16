# -*- coding: utf-8 -*-
"""示例共用：让中文在 Windows（cp1252）、C locale 等非 UTF-8 终端下也能正常打印。

不改库的 stdout 行为，只在示例入口调用；被重定向到文件时同样有效。
"""
import sys


def utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
