"""
処理内容を書きこんだファイルを入力フォルダに入れることで、外部からオーダーできる機能

ファイル名: replayresizer_order_(任意).txt
内容形式:
    [option1]
    [option2]...
    (in_path)[>(out_path/out_name)]

オプション:
    delete_source_when_complete
    disable_popup

"""
import os
import re
from logging import getLogger
from pathlib import Path
from typing import Optional

from replayresizer.entry import ResizeEntry, OrderOption

log = getLogger(__name__)
ALLOW_NAME = re.compile(r"^replayresizer_order_(.+)\.txt$")


class OrderScriptManager(object):
    def __init__(self):
        pass

    @staticmethod
    def process_script_entry(file: Path, *, size_limit: int) -> Optional[ResizeEntry]:
        m = ALLOW_NAME.search(file.name)
        if m is None:
            return

        with file.open(encoding="utf-8") as f:
            args = [line.strip() for line in f if line.strip()]

        log.info("script args: '" + "', '".join(args) + "'")

        log.debug(f"deleting script file: {file}")
        try:
            # noinspection PyTypeChecker
            os.remove(file)
        except OSError as e:
            log.warning(f"failed to delete: {e}")

        tmp = args.pop(-1).split(">")
        args = [a.lower() for a in args]
        source = tmp[0]
        try:
            target = tmp[1]
        except IndexError:
            target = None

        entry = ResizeEntry(Path(source), size_limit=size_limit)
        entry.is_script_order = True
        entry.custom_outname = target
        entry.order_filename = file

        if "disable_popup" in args:
            entry.order_options |= OrderOption.DISABLE_POPUP

        if "delete_source_when_complete" in args:
            entry.order_options |= OrderOption.DELETE_SOURCE_WHEN_COMPLETE

        return entry
