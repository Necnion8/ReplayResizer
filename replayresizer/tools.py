import io
import os
import subprocess
import threading
from logging import getLogger
from pathlib import Path
from typing import Union

import sys


__all__ = ["get_file_size", "get_file_size_label", "get_bit_rate_label", "open_explorer",
           "colour_to_color16", "color16_to_colour", "get_codec_name", "is_windows",
           "subprocess_startup_info", "WithLock", "BackgroundTask",
           "IOLogger"
           ]


def get_file_size(path: Union[str, Path]):
    """K-bytes"""
    return os.path.getsize(str(path)) / 1024


def get_file_size_label(size_kb: float):
    if size_kb < 1150:
        size_text = f"{round(size_kb)} KB"
    elif size_kb < 1150 ** 2:
        size_text = f"{round(size_kb / 1024, 1)} MB"
    else:
        size_text = f"{round(size_kb / (1024 ** 2), 1)} GB"
    return size_text


def get_bit_rate_label(bit_rate: int):
    if bit_rate < 1150:
        bit_rate_text = f"{round(bit_rate)} bps"
    elif bit_rate < 1150 ** 2:
        bit_rate_text = f"{round(bit_rate / 1000, 1)} Kbps"
    else:
        bit_rate_text = f"{round(bit_rate / (1000 ** 2), 1)} Mbps"
    return bit_rate_text


def open_explorer(path: Union[str, Path], *, select=False):
    if is_windows():
        path = Path(path).resolve()
        if select:
            subprocess.Popen(f"explorer /select,\"{path}\"")
        else:
            subprocess.Popen(f"explorer \"{path}\"")


def is_windows():
    return sys.platform == "win32"


def subprocess_startup_info():
    startup_info = None
    if is_windows():
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return startup_info


def color16_to_colour(color: int):
    value = ("000000" + hex(color)[2:])[-6:]
    try:
        color = tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        color = (255, 255, 255)
    from wx import Colour
    return Colour(*color)


def colour_to_color16(colour):
    """
    :type colour: wx.Colour
    """
    text = hex(colour.Red())[2:]
    text += hex(colour.Green())[2:]
    text += hex(colour.Blue())[2:]
    return int(text, 16)


def get_codec_name(codec: str):
    if codec == "h264":
        return "H.264"
    elif codec == "vp9":
        return "VP9"
    elif codec == "hevc":
        return "H.265"
    elif codec == "mpeg2video":
        return "MPEG-2"
    return codec


class WithLock:
    def __init__(self):
        self.lock = threading.Lock()

    def __enter__(self):
        self.lock.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()


class BackgroundTask(threading.Thread):
    def __init__(self, task, done):
        threading.Thread.__init__(self, daemon=True)
        self.task = task
        self.done = done

    def run(self) -> None:
        try:
            result = self.task()
        except (Exception,):
            getLogger(__name__).exception("exception in background task")
            return

        from wx import CallAfter
        CallAfter(lambda: self.done(result))


class IOLogger(io.StringIO):
    def __init__(self, *, name: str, method):
        io.StringIO.__init__(self)
        self._method = method
        self._name = name

    def write(self, s: str) -> int:
        s = s[:-s.endswith("\n") or None]

        for line in s.splitlines():
            self._method("[%s]: %s", self._name, line)
        return len(s)
