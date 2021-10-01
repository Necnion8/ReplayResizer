import os
import re
import subprocess
import traceback
from logging import getLogger
from pathlib import Path
from typing import Optional, Tuple

from replayresizer.tools import get_file_size

log = getLogger(__name__)


class OrderOption:
    NONE = 0b0
    DISABLE_POPUP = 0b1
    DELETE_SOURCE_WHEN_COMPLETE = 0b10


class MediaInfo:
    def __init__(self, **info):
        self.info = info
        self.peak_gain = None  # type: Optional[float]

        self._frame_rate = None
        self._wh = None

    @property
    def duration(self) -> float:
        return float(self.info["duration"])

    @property
    def bit_rate(self) -> Optional[int]:
        return int(self.info["bit_rate"]) if "bit_rate" in self.info else None

    @property
    def frame_rate(self) -> Optional[float]:
        if self._frame_rate is None and "avg_frame_rate" in self.info:
            m = re.search(r"(\d+)/(\d+)", self.info["avg_frame_rate"])
            if m:
                self._frame_rate = round(int(m.group(1)) / int(m.group(2)), 1)

        return self._frame_rate

    @property
    def scale_wh(self) -> Tuple[int, int]:
        if not self._wh and "width" in self.info and "height" in self.info:
            self._wh = (int(self.info["width"]), int(self.info["height"]))
        elif not self._wh and "coded_width" in self.info and "coded_height" in self.info:
            self._wh = (int(self.info["coded_with"]), int(self.info["coded_height"]))
        return self._wh or (0, 0)

    @property
    def codec_name(self) -> str:
        return str(self.info.get("codec_name", "n/a"))


class ResizeEntry(object):
    def __init__(self, source: Path, *, size_limit: int):
        self.source = source
        self.size_limit = size_limit

        self.source_size = get_file_size(source) if source.is_file() else 0
        self.media_info = None  # type: Optional[MediaInfo]

        self.resized = None  # type: Optional[Path]
        self.resized_size = None  # type: Optional[float]

        # encode settings
        self.preset_name = ""
        self.bit_rate = 0
        self.frames = 0
        self.width = 0
        self.height = 0
        self.size_adjust = 100
        self.encoder_params = ""
        self.fix_gain = None  # type: Optional[float]
        self.audio_codec = ""
        self.video_codec = ""
        self.ext = ""
        self.encode_progress = 0  # type: Optional[float]
        self.size_adjust_first = 100

        self.is_script_order = False
        self.order_options = 0
        self.custom_outname = None
        self.order_filename = None  # type: Optional[Path]

        # cache
        self.thumbnail_cache = None  # wx.Bitmap
        self.process = None  # type: Optional[subprocess.Popen]
        self.completed = False
        self.skipped = False

    @property
    def is_encoding(self) -> bool:
        return self.process is not None and self.process.returncode is None

        pass

    # @property
    # def completed(self):
    #     return (self.resized and self.resized_size) or (self.source_size <= self.size_limit)

    @property
    def complete_file(self) -> Optional[Path]:
        if self.is_encoding:
            return None
        elif self.resized and self.resized_size:
            return self.resized
        elif self.source_size <= self.size_limit:
            return self.source

    @property
    def complete_file_size(self) -> Optional[int]:
        if self.is_encoding:
            return None
        elif self.resized and self.resized_size:
            return self.resized_size
        elif self.source_size <= self.size_limit:
            return self.source_size

    def __repr__(self):
        return f"<{type(self).__name__} source={self.source.name!r} resized={bool(self.resized) and bool(self.resized_size)}>"

    def delete_source_file(self):
        if self.source.is_file():
            log.debug(f"deleting source file: {self.source}")
            try:
                # noinspection PyTypeChecker
                os.remove(self.source)
            except OSError as e:
                log.warning(f"failed to delete: {e}")

    def delete_resize_file(self):
        if self.resized and self.resized.is_file():
            log.debug(f"deleting resized file: {self.resized}")
            try:
                # noinspection PyTypeChecker
                os.remove(self.resized)
            except OSError as e:
                log.warning(f"failed to delete: {e}")


class PopupMessage(object):
    def __init__(self, title: str, hide_delay: Optional[int] = 5, *, description: str = None, content: str = None):
        self.title = title
        self.hide_delay = hide_delay
        self.description = description
        self.content = content

    def with_traceback(self, exc: Exception):
        lines = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip().splitlines()
        reg = re.compile(r"^ +File \"(.+)\", line \d+, in .*$")

        root = Path(__file__).resolve().parent.parent  # type: Path

        for idx, line in enumerate(lines):
            m = reg.search(line)
            if not m:
                continue

            path = Path(m.group(1)).resolve()
            try:
                path = path.relative_to(root)
            except ValueError:
                path = m.group(1)[-30:]

            start, end = m.span(1)
            lines[idx] = f"{line[:start]}{path}{line[end:]}"

        self.content = "\n".join(lines)
        return self
