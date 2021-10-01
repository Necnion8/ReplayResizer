import json
import logging
import os
import re
import shlex
import subprocess
import sys
from logging import getLogger
from pathlib import Path
from typing import Dict, Tuple, List, Optional, Set

import wx.adv
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
from watchdog.observers import Observer

from replayresizer.config import AppConfiguration, AutoActionWhen, CloseAction
from replayresizer.entry import ResizeEntry, MediaInfo, PopupMessage, OrderOption
from replayresizer.errors import ProcessCodeError
from replayresizer.orderscript import OrderScriptManager
from replayresizer.popup_panel import PopupPanel
from replayresizer.settings_panel import SettingsFrame
from replayresizer.taskbar import TaskBar
from replayresizer.tools import *

CONFIG_FILE = Path("appconfig.json")
FRAME_TITLE = "リプレイリサイザ"
VERSION = "1.0.0/210512"
TB_MENU_EXIT = wx.NewId()
TB_MENU_PAUSE = wx.NewId()
TB_MENU_OPEN_SETTINGS = wx.NewId()
TB_MENU_OPEN_INPUT_DIRECTORY = wx.NewId()
TB_MENU_OPEN_OUTPUT_DIRECTORY = wx.NewId()
TB_MENU_OPEN = wx.NewId()

log = getLogger(__name__)


class ReplayResizer(FileSystemEventHandler):
    def __init__(self, app: wx.App):
        self.app = app
        self.config = AppConfiguration(CONFIG_FILE)
        self.script = OrderScriptManager()
        # create taskbar
        self.taskbar = TaskBar()
        self.taskbar.CreatePopupMenu = self.CreatePopupMenu
        self.taskbar.Bind(wx.EVT_MENU, self.on_menu)
        self.taskbar.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, lambda _: self.show_panel())
        # watchdog
        self.observer = None  # type: Optional[Observer]
        self.watched_files = set()  # type: Set[Path]  # 監視中、録画完了待ち
        self.delayed_files = dict()  # type: Dict[Path, wx.CallLater]  # 監視遅延待機中
        self.entries = list()  # type: List[ResizeEntry]  # キューされたエントリ
        self.current_entry = None  # type: Optional[ResizeEntry]  # 処理中
        self.lock = WithLock()
        # create frame
        self.main_panel = PopupPanel(self, self.config)
        self.settings_frame = None  # type: Optional[SettingsFrame]
        #
        self._pause_menu = False
        self._app_instance = wx.SingleInstanceChecker()

        try:
            import pynput
            from replayresizer.keylistener import KeyListener

        except ImportError:
            self.key_listener = None
            log.warning("shift key listener is disabled! (pynput modules not installed)")
        else:
            self.key_listener = KeyListener(self.main_panel)
            self.key_listener.start()

    # main

    def launch(self, args):
        try:
            self.config.load_from_json_file(save_default=False)
        except json.JSONDecodeError as e:
            log.exception("exception in load_from_json_file")
            self.main_panel.draw_message(None, PopupMessage(
                "設定ファイルを読み込めませんでした",
                description=str(e),
                hide_delay=None,
            ).with_traceback(e))
            return

        # if self.config.setup:
        #     pass

        if not self.check_ffmpeg():
            # self.main_panel.draw_message(None, PopupMessage("ffmpeg / ffprobe を利用できません", hide_delay=None))
            dialog = wx.MessageDialog(
                self.main_panel.frame,
                message="FFmpeg / ffprobe を設定してください。",
                caption="リプレイリサイザ",
                style=wx.OK | wx.CANCEL
            )
            if dialog.ShowModal() == wx.ID_OK:
                self.open_settings()
                return

            else:
                wx.Exit()
            dialog.Destroy()

        self.taskbar.show()
        self.main_panel.title.SetBackgroundColour(color16_to_colour(self.config.color))

        if "openrun" in args:
            self.main_panel.frame.Show()

        if not self.config.pause:
            self.start_watchdog()

        if self.config.first_start:
            self.config.first_start = False
            self.show_panel()
            self.config.save_to_json_file()

    def start_watchdog(self):
        self.stop_watchdog()

        # TODO: all check script

        if self.config.input_directory and Path(self.config.input_directory).is_dir():
            self.observer = Observer()
            self.observer.setDaemon(True)
            self.observer.schedule(self, self.config.input_directory)
            log.info("observer started: %s", self.config.input_directory)
            self.observer.start()

    def stop_watchdog(self):
        if self.observer is not None:
            log.debug("stopping observer")
            try:
                if self.observer.is_alive():
                    self.observer.stop()
                    self.observer.join(2)
            except (Exception,):
                log.exception("exception in observer shutdown")
            else:
                log.info("observer stopped")

            self.observer = None

        self.watched_files.clear()
        for timer in self.delayed_files.values():
            timer.Stop()
        self.delayed_files.clear()

    def exit(self):
        self.main_panel.Hide()
        self.taskbar.RemoveIcon()
        self.taskbar.Destroy()
        self.stop_watchdog()

        if self.key_listener:
            try:
                self.key_listener.stop()
                self.key_listener.join(1)
            except (Exception,):
                log.warning("error in keyListener.stop", exc_info=True)

        wx.Exit()
        pass

    def on_recorded(self, path: Path):
        if not path.is_file():
            return

        if self.current_entry:
            if self.current_entry.source.resolve() == path.resolve():
                log.warning(f"ignore queuing for running file: {path}")
                return

        for _entry in self.entries:
            if _entry.source.resolve() == path.resolve():
                log.warning(f"ignore queuing for already queued: {path}")
                return

        entry = ResizeEntry(path, size_limit=self.config.size_limit)
        self.add_entry(entry)

    def add_entry(self, entry: ResizeEntry):
        log.info(f"queueing: {entry.source.name!r}")
        if entry.is_script_order:
            log.info(f"  is order: {entry.order_filename!r}")

        log.debug("A")
        with self.lock:
            log.debug("B")
            if self.current_entry or self.is_paused_menu:
                log.debug("C")
                log.debug(f"current:{self.current_entry!r} isPausedMenu:{self.is_paused_menu!r}")
                self.entries.append(entry)
            else:
                log.debug("D")
                try:
                    self.process(entry)
                except (Exception,):
                    log.exception("exception in process entry")

    def show_panel(self):
        if not self.is_paused_menu:
            self.main_panel.draw_entry(self.current_entry)
            self.main_panel.frame.Show()

    def open_input_directory(self):
        if self.config.input_directory and Path(self.config.input_directory).is_dir():
            open_explorer(self.config.input_directory)

    # events

    def on_created(self, event: FileCreatedEvent):
        log.debug("onCreated: %s (%s)", event.src_path, get_file_size_label(get_file_size(event.src_path)))
        self.watched_files.add(Path(event.src_path))

    def on_modified(self, event: FileModifiedEvent):
        try:
            log.debug("onModified: %s (%s)", event.src_path, get_file_size_label(get_file_size(event.src_path)))
        except FileNotFoundError:
            return

        try:
            path = Path(event.src_path)

            entry = self.script.process_script_entry(path, size_limit=self.config.size_limit)
            if entry:
                self.add_entry(entry)
                return

            try:
                self.watched_files.remove(path)
            except KeyError:
                return

            if self.check_filename(path):
                if 0 < self.config.listen_delay:
                    if path in self.delayed_files:
                        self.delayed_files[path].Stop()

                    def _in_main_thread():
                        self.delayed_files[path] = wx.CallLater(self.config.listen_delay * 1000, self.on_recorded, path)

                    wx.CallAfter(_in_main_thread)

                else:
                    self.on_recorded(path)

        except (Exception,):
            log.exception("")

    def CreatePopupMenu(self, event=None):
        m = wx.Menu()
        m.Append(TB_MENU_OPEN, "開く (&O)"
                 ).Enable(not self.is_paused_menu)
        m.Append(TB_MENU_OPEN_INPUT_DIRECTORY, "キャプチャフォルダを開く (&C)"
                 ).Enable(bool(self.config.input_directory and Path(self.config.input_directory).is_dir()))
        m.Append(TB_MENU_OPEN_OUTPUT_DIRECTORY, "出力フォルダを開く (&O)"
                 ).Enable(bool(self.config.output_directory and Path(self.config.output_directory).is_dir()))
        m.AppendSeparator()
        m.AppendCheckItem(
            TB_MENU_PAUSE, "ファイルを監視しない (&P)"
        ).Check(self.config.pause)
        m.Append(TB_MENU_OPEN_SETTINGS, "設定を開く (&O)"
                 ).Enable(self.current_entry is None)
        m.Append(TB_MENU_EXIT, "終了 (&E)")
        return m

    def on_menu(self, event: wx.CommandEvent):
        if event.GetId() == TB_MENU_OPEN:
            self.show_panel()

        elif event.GetId() == TB_MENU_OPEN_INPUT_DIRECTORY:
            self.open_input_directory()

        elif event.GetId() == TB_MENU_OPEN_OUTPUT_DIRECTORY:
            if self.config.output_directory and Path(self.config.output_directory).is_dir():
                open_explorer(self.config.output_directory)

        elif event.GetId() == TB_MENU_PAUSE:
            self.config.pause = not self.config.pause

            if self.config.pause:
                self.stop_watchdog()
            else:
                self.start_watchdog()

            self.config.save_to_json_file()

        elif event.GetId() == TB_MENU_OPEN_SETTINGS and self.current_entry is None:
            self.open_settings()

        elif event.GetId() == TB_MENU_EXIT:
            try:
                self.exit()
            finally:
                wx.Exit()

    #

    def process(self, entry: ResizeEntry):
        if self.current_entry:
            raise RuntimeError(f"Already set current entry: {self.current_entry!r}")

        if not self.check_ffmpeg():
            self.main_panel.draw_message(None, PopupMessage(
                "ffmpeg / ffprobe を利用できません"
            ))
            return

        self.current_entry = entry
        log.info(f"Resize START: {entry!r}")

        self.main_panel.draw_entry(entry)  # blank & draw file size
        self.taskbar.show(progress=0)
        # self.main_panel.update_buttons()
        if self.config.silent_popup or entry.order_options & OrderOption.DISABLE_POPUP:
            self.main_panel.frame.Show(False)
        else:
            self.main_panel.frame.Show(True)

        BackgroundTask(lambda: self._process_sync(entry), lambda r: None).start()

    def _process_sync(self, entry: ResizeEntry):
        try:
            json_info = self.get_media_info(entry.source)
        except ProcessCodeError as e:
            if entry.is_script_order and entry.order_options | OrderOption.DISABLE_POPUP:
                return

            self.main_panel.async_draw_message(entry, PopupMessage(
                f"メディア情報を取得できません (終了コード {e.return_code})",
                description=entry.source.name,
            ))
            return
        except Exception as e:
            if entry.is_script_order and entry.order_options | OrderOption.DISABLE_POPUP:
                return

            self.main_panel.async_draw_message(entry, PopupMessage(
                "メディア情報を取得できませんでした",
            ).with_traceback(e))
            return

        if not json_info:
            if entry.is_script_order and entry.order_options | OrderOption.DISABLE_POPUP:
                return

            if not self.config.ignore_error:
                self.main_panel.async_draw_message(entry, PopupMessage(
                    "ビデオストリームがありません",
                    description=entry.source.name,
                ))
            return

        entry.media_info = MediaInfo(**json_info)

        if self.config.thumbnail:
            def complete_thumbnail(bmp):
                entry.thumbnail_cache = bmp
                self.main_panel.draw_entry(entry)

            BackgroundTask(
                lambda: self.get_thumbnail_bitmap(
                    entry.source, int(entry.media_info.duration * .25),
                    tuple(self.main_panel.thumbnail.GetSize())
                ), complete_thumbnail
            ).start()

        if not entry.is_script_order and entry.source_size <= self.config.size_limit:
            entry.completed = True
            wx.CallAfter(lambda: self._on_finished(entry))
            return

        def go_encode():
            self.apply_encode_params(entry)
            self.main_panel.draw_entry(entry)

            if entry.bit_rate < 16:
                self.main_panel.async_draw_message(entry, PopupMessage(
                    "動画が長すぎます... X(",
                    description=f"出力ビットレート:  {'-'if entry.bit_rate < 0 else ''}{get_bit_rate_label(abs(entry.bit_rate))}"
                ))
                return
            BackgroundTask(lambda: self.encode(entry), lambda r: None).start()

        if self.config.normalized_volume:
            log.debug("peak gain ...")

            def complete_gain(gain):
                entry.media_info.peak_gain = gain
                go_encode()

            BackgroundTask(
                lambda: self.get_peak_gain(entry.source),
                complete_gain
            ).start()

        else:
            wx.CallAfter(lambda: go_encode())

    def _on_finished(self, entry):
        log.debug("onFinished")
        self.taskbar.show()

        self.action_count_lefts = -1

        if self.config.auto_close_when_enum == AutoActionWhen.ON_COMPLETED:
            self.main_panel.start_action_timer()
            self.main_panel.update_buttons()

        self.main_panel.draw_entry(entry)
        self.main_panel.frame.Show()

    def call_close_action(self, *, shift=False):
        self.main_panel.hide_message_flag()

        entry = self.current_entry
        if not entry or entry.is_encoding:
            log.debug("call_close_action -> not entry or is_encoding")
            self.main_panel.frame.Hide()
            return

        elif not entry.completed:
            log.debug("call_close_action -> not encoding and not completed (errors?)")

        else:  # completed
            action = self.config.close_action_enum if not shift else self.config.close_action_shift_enum
            log.debug(f"call_close_action -> completed action={action} shift={shift}")

            if action == CloseAction.CLOSE_AND_DELETE_SOURCE or action == CloseAction.CLOSE_AND_DELETE_ALL:
                entry.delete_source_file()

            if action == CloseAction.CLOSE_AND_DELETE_RESIZE or action == CloseAction.CLOSE_AND_DELETE_ALL:
                entry.delete_resize_file()

        self.next_entry()

    def next_entry(self):
        log.debug("fire")
        self.taskbar.show()

        with self.lock:
            self.current_entry = None

            if self.is_paused_menu:
                log.debug("next_entry -> ignored by pause")
                return

            try:
                entry = self.entries.pop(0)
            except IndexError:
                self.main_panel.frame.Hide()
                self.main_panel.draw_entry(None)
            else:
                self.process(entry)

    def skip_current_entry(self):
        if self.current_entry and self.current_entry.is_encoding:
            log.info("ffmpeg canceling...")
            self.current_entry.skipped = True
            self.current_entry.process.communicate(b"q")
            log.info("send Quit")

    def pause_menu(self, *, paused: bool) -> bool:
        if self._pause_menu == paused:
            return True

        if paused:
            if self.current_entry is None:
                self._pause_menu = True
                return True
        else:
            self._pause_menu = False
            self.call_main_thread(self.next_entry)
            return True
        return False

    @property
    def is_paused_menu(self):
        return self._pause_menu

    def open_settings(self):
        if self.settings_frame is None:
            if not self.pause_menu(paused=True):
                return
            self.settings_frame = SettingsFrame(self.main_panel.frame, self.config)
            self.settings_frame.CentreOnParent()
            self.settings_frame.Show()
            self.main_panel.frame.Hide()

            def _close(*_):
                if self.settings_frame.result:
                    self.main_panel.title.SetBackgroundColour(color16_to_colour(self.config.color))
                    self.main_panel.draw_entry(self.current_entry)
                    self.main_panel.Refresh()

                    if self.config.first_start:
                        self.config.first_start = False
                        self.config.save_to_json_file()
                        self.show_panel()

                    if self.settings_frame.changed_input:
                        self.start_watchdog()

                self.settings_frame.Destroy()
                self.settings_frame = None
                self.pause_menu(paused=False)

            self.settings_frame.Bind(wx.EVT_CLOSE, _close)

        else:
            self.settings_frame.SetFocus()

    #

    def check_filename(self, source: Path):
        for regex in self.config.active_targets:
            if regex.search(source.name):
                break
        else:
            return False

        for regex in self.config.active_ignores:
            if regex.search(source.name):
                return False

        return True

    def calc_bit_rate(self, duration: float, adjust: float, audio_rate: int):
        return self.config.size_limit * 1000 / duration / 128 * adjust - audio_rate

    def apply_encode_params(self, entry: ResizeEntry):
        if entry.media_info is None:
            raise ValueError("media_info is None!")

        info = entry.media_info
        limit_size = self.config.size_limit

        rate = limit_size * 1000 / info.duration / 128 - 96
        if rate >= self.config.hq_bitrate:  # HQ
            entry.width = self.config.hq_width
            entry.height = self.config.hq_height
            entry.frames = 30 if info.frame_rate > 36 and self.config.hq_fps30 else 0
            entry.encoder_params = self.config.hq_encoder_params
            entry.bit_rate = self.calc_bit_rate(info.duration, self.config.hq_size_adjust / 100, 0)
            entry.preset_name = "VP9 (HQ)"
            if self.config.hq_no_audio:
                entry.audio_codec = None
            else:
                entry.audio_codec = "libopus"
                entry.bit_rate -= 96
            entry.video_codec = "libvpx-vp9"
            entry.ext = "webm"
            entry.size_adjust = entry.size_adjust_first = self.config.hq_size_adjust

        elif rate < self.config.ulq_bitrate:  # ULQ
            entry.width = self.config.ulq_width
            entry.height = self.config.ulq_height
            entry.frames = 16 if info.frame_rate > 20 and self.config.ulq_fps16 else 0
            entry.encoder_params = self.config.ulq_encoder_params
            entry.bit_rate = self.calc_bit_rate(info.duration, self.config.ulq_size_adjust / 100, 0)
            entry.preset_name = "H.264 (ULQ)"
            entry.video_codec = "libx264"
            entry.ext = "mp4"
            entry.size_adjust = entry.size_adjust_first = self.config.ulq_size_adjust
            if self.config.ulq_no_audio:
                entry.audio_codec = None
            else:
                entry.audio_codec = "aac"
                entry.bit_rate -= 96

        else:  # LQ
            entry.width = self.config.lq_width
            entry.height = self.config.lq_height
            entry.frames = 30 if info.frame_rate > 36 and self.config.lq_fps30 else 0
            entry.encoder_params = self.config.lq_encoder_params
            entry.bit_rate = self.calc_bit_rate(info.duration, self.config.lq_size_adjust / 100, 0)
            entry.preset_name = "H.264 (LQ)"
            entry.video_codec = "libx264"
            entry.ext = "mp4"
            entry.size_adjust = entry.size_adjust_first = self.config.lq_size_adjust
            if self.config.lq_no_audio:
                entry.audio_codec = None
            else:
                entry.audio_codec = "aac"
                entry.bit_rate -= 96

        if self.config.normalized_volume and info.peak_gain is not None:
            limit_db = self.config.volume_normalize_limit_db
            gain = self.config.volume_db - info.peak_gain
            gain = max(-limit_db, min(limit_db, gain))

            if abs(gain) >= 2.5:
                entry.fix_gain = gain

    # noinspection PyMethodMayBeStatic
    def finish_script(self, entry: ResizeEntry):
        if entry.order_options & OrderOption.DELETE_SOURCE_WHEN_COMPLETE:
            entry.delete_source_file()

    # ffmpeg

    def check_ffmpeg(self):
        try:
            if subprocess.Popen(
                [self.config.ffmpeg_command, "-version"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                startupinfo=subprocess_startup_info()
            ).wait() != 0:
                return False

            return subprocess.Popen(
                [self.config.ffprobe_command, "-version"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                startupinfo=subprocess_startup_info()
            ).wait() == 0

        except (Exception,):
            return False

    def get_media_info(self, path: Path):
        p = subprocess.Popen(
            [self.config.ffprobe_command, "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            startupinfo=subprocess_startup_info()
        )
        return_code = p.wait()
        if return_code != 0:
            log.error(f"get_media_info() returned {return_code} code!")
            lines = []
            for line in p.stdout:
                line = line.decode(errors='ignore').rstrip()
                log.debug(f" > {line}")
                lines.append(line)

            lines = "\n".join(lines)
            raise ProcessCodeError(p, lines)

        for stream in json.load(p.stdout)["streams"]:
            if stream.get("codec_type") == "video":
                log.debug(f"get_media_info: {stream}")

                if stream.get("codec_name") == "vp9":
                    m = re.search(r"^(\d{2}):(\d{2}):(\d{2})\.(\d*)$", stream.get("tags", {}).get("DURATION", ""))
                    if m:
                        duration = int(m.group(1)) * 60 * 60
                        duration += int(m.group(2)) * 60
                        duration += int(m.group(3))
                        stream["duration"] = duration

                return stream

    def get_thumbnail_bitmap(self, path: Path, location: int, size: Tuple[int, int]):
        tmp_name = "thumbnail.tmp"

        try:
            subprocess.Popen(
                [self.config.ffmpeg_command, "-v", "quiet", "-ss", str(location), "-i", str(path),
                 "-vframes", "1", "-f", "image2", "-s", f"{size[0]}x{size[1]}", "-y", tmp_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=subprocess_startup_info()
            ).wait()

            if Path(tmp_name).is_file():
                try:
                    return wx.Bitmap("thumbnail.tmp")
                finally:
                    os.remove(tmp_name)
        except (Exception,):
            log.warning("exception in get_thumbnail (ignored)")

    def get_peak_gain(self, path: Path):
        log.debug("start gain detect")
        try:
            p = subprocess.Popen(
                [self.config.ffmpeg_command, "-hide_banner", "-i", str(path),
                 "-af", "volumedetect", "-vn", "-sn", "-dn", "-f", "null", "/dev/null"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                startupinfo=subprocess_startup_info()
            )
            reg = re.compile(r"max_volume: (-?\d+\.\d*) dB")
            for line in p.stderr:
                line = line.decode(errors="ignore").rstrip()
                log.debug(f" > {line}")
                m = reg.search(line)
                if m:
                    return float(m.group(1))
        except (Exception,):
            log.warning("exception in gain detect (ignored)", exc_info=True)

    def encode(self, entry: ResizeEntry, *, retry=0):
        if entry.process and entry.process.returncode == -1:
            raise RuntimeError("already running encode process!")

        command_args = [self.config.ffmpeg_command, "-hide_banner", "-progress", "pipe:1",
                        "-i", str(entry.source)]

        if entry.audio_codec:
            command_args.extend(["-c:a", entry.audio_codec,
                                 "-b:a", "96k", "-minrate:a", "96k", "-maxrate:a", "96k", "-ac", "2"])
            if entry.fix_gain:
                command_args.extend(["-af", f"volume={entry.fix_gain}dB"])

        command_args.extend([
            "-c:v", entry.video_codec,
            "-b:v", f"{round(entry.bit_rate, 2)}k",
            "-minrate:v", f"{round(entry.bit_rate, 2)}k",
            "-maxrate:v", f"{round(entry.bit_rate, 2)}k",
        ])
        filters = []
        if entry.width or entry.height:
            width = entry.width if entry.width >= 1 else -2
            height = entry.height if entry.height >= 1 else -2
            filters.append(f"scale={width}:{height}")
        if entry.frames:
            filters.append(f"fps={entry.frames}")

        if filters:
            command_args.extend(["-vf", ",".join(filters)])

        if entry.encoder_params:
            command_args.extend(shlex.split(entry.encoder_params))

        # output name
        output = Path(self.config.output_directory)

        if entry.custom_outname:
            output = output / Path(entry.custom_outname + "." + entry.ext)
            output.parent.mkdir(parents=True, exist_ok=True)

        else:
            output.mkdir(parents=True, exist_ok=True)

            if output.resolve() != Path(self.config.input_directory).resolve():
                output = Path(output / entry.source.name).with_suffix("." + entry.ext)
            else:
                try:
                    _filename = self.config.rename_format.format(name=entry.source.stem, ext=entry.ext)
                except KeyError as e:
                    log.warning(f"rename format error: {e}")
                    _filename = "{name}_resized.{ext}".format(name=entry.source_size.stem, ext=entry.ext)

                output = Path(output / _filename)

        command_args.extend(["-y", str(output)])
        entry.resized = output
        entry.resized_size = 0

        log.info(f"start encode: {entry}")
        log.debug(f"encode command_line: '%s'", "' '".join(command_args))

        time_reg = re.compile(r"out_time_ms=(\d+)")
        size_reg = re.compile(r"total_size=(\d+)")

        stdout = []

        p = None
        try:
            entry.process = p = subprocess.Popen(
                command_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                startupinfo=subprocess_startup_info()
            )

            for line in p.stdout:
                line = line.decode(errors="ignore").rstrip()
                stdout.append(line)
                log.debug(f" > {line}")

                m = time_reg.search(line)
                if m:
                    duration = int(m.group(1)) / 1000000
                    entry.encode_progress = duration / entry.media_info.duration

                m = size_reg.search(line)
                if m:
                    size_kb = int(m.group(1)) / 1024
                    entry.resized_size = size_kb

                if line.lower() == "progress=continue":
                    wx.CallAfter(lambda: self.main_panel.draw_entry(entry))
                    wx.CallAfter(lambda: self.taskbar.show(progress=round(entry.encode_progress * 100)))

            return_code = p.wait()

        except Exception as e:
            log.exception("exception in encoder read process")
            entry.encode_progress = None
            if p:
                p.wait()

            popup_message = True
            if entry.is_script_order:
                popup_message = not bool(entry.order_options & OrderOption.DISABLE_POPUP)
                self.finish_script(entry)

            if popup_message:
                self.main_panel.async_draw_message(entry, PopupMessage(
                    "内部エラーが発生しました",
                    description="詳細はログファイルを参照してください。"
                ).with_traceback(e))
            else:
                wx.CallAfter(self.next_entry)

        else:
            wx.CallAfter(lambda: self.taskbar.show(progress=100))
            log.info(f"complete encode: {entry}")
            log.info(f"return-code: {return_code}")

            # if entry.order_options & OrderOption.DELETE_SOURCE_WHEN_COMPLETE:
            #     entry.delete_source_file()

            if entry.skipped:
                log.info("skipped! (go next)")
                entry.delete_resize_file()

                if entry.is_script_order:
                    self.finish_script(entry)

                wx.CallAfter(lambda: self.next_entry())
                return

            if return_code != 0:
                entry.encode_progress = None
                wx.CallAfter(lambda: self.main_panel.draw_entry(entry))

                popup_message = True
                if entry.is_script_order:
                    popup_message = not bool(entry.order_options & OrderOption.DISABLE_POPUP)
                    self.finish_script(entry)

                if popup_message:
                    self.main_panel.async_draw_message(entry, PopupMessage(
                        f"処理プロセスが コード {p.returncode} で終了しました",
                        description=entry.source.name,
                        content="\n".join(stdout)
                    ))
                else:
                    wx.CallAfter(self.next_entry)
                return

            entry.resized_size = get_file_size(output)
            entry.encode_progress = 1
            wx.CallAfter(lambda: self.main_panel.draw_entry(entry))

            if entry.resized_size > self.config.size_limit:
                log.warning(f"OVER SIZE LIMIT ({entry.resized_size} <= {self.config.size_limit})")
                if retry < 2:
                    log.warning(f"retrying... ({retry + 1})")

                    resized = entry.resized_size
                    target = self.config.size_limit
                    adjust = entry.size_adjust

                    over = resized - target
                    over_per = 1 - over / target
                    new_adjust = adjust * over_per * over_per

                    log.info(f"ReResize adjust: {adjust}% -> {new_adjust}%")

                    entry.size_adjust = new_adjust
                    entry.bit_rate = self.calc_bit_rate(
                        entry.media_info.duration,
                        new_adjust / 100, 96 if entry.audio_codec else 0
                    )
                    self.encode(entry, retry=retry + 1)
                    return

            entry.completed = True
            wx.CallAfter(lambda: self._on_finished(entry))

            if entry.is_script_order:
                self.finish_script(entry)

    # static

    @staticmethod
    def setup_logging(level=logging.DEBUG):
        root = logging.getLogger("replayresizer")
        root.setLevel(logging.DEBUG)

        if sys.__stderr__ is not None:  # call not in pythonW
            sh = logging.StreamHandler(sys.__stderr__)
            sh.setFormatter(logging.Formatter(
                "[%(levelname)s,%(funcName)s:%(lineno)d,%(threadName)s] %(message)s"))
            sh.setLevel(level)
            root.addHandler(sh)

        sys.stdout = IOLogger(name="stdout", method=log.info)
        sys.stderr = IOLogger(name="stderr", method=log.error)

        try:
            with open("latest.log", "w") as _:
                pass  # clean latest.log
            fh = logging.FileHandler("latest.log", encoding="utf-8", delay=False)
            fh.setFormatter(logging.Formatter(
                "%(asctime)s,%(levelname)s,%(filename)s,%(funcName)s:%(lineno)d,%(threadName)s,%(message)s"))
            root.addHandler(fh)
        except OSError:
            log.exception("setup error: file log handler")

    @staticmethod
    def load_icon():
        return wx.Icon("icon.ico")

    @staticmethod
    def call_main_thread(func, *args, **kwargs):
        wx.CallAfter(lambda: func(*args, **kwargs))


