import time
from logging import getLogger
from pathlib import Path
from typing import Optional

import wx.adv

from replayresizer import layout
from replayresizer.config import AutoActionWhen, CloseAction
from replayresizer.entry import ResizeEntry, PopupMessage, OrderOption
from replayresizer.images import icon
from replayresizer.keyhandler import KeyHandler
from replayresizer.tools import *

try:
    from pynput.keyboard import Key
except ImportError:
    Key = None

log = getLogger(__name__)


class FileDropTarget(wx.FileDropTarget):
    def __init__(self, func):
        wx.FileDropTarget.__init__(self)
        self._func = func

    def OnDropFiles(self, x, y, filenames):
        return self._func(x, y, filenames)


class PopupPanel(layout.PopupPanel, KeyHandler):
    def __init__(self, app, config):
        """
        :type app: replayresizer.replayresizer.ReplayResizer
        :type config: replayresizer.config.AppConfiguration
        """
        self.app = app
        self.config = config
        self.frame = wx.Frame(None, -1, "リプレイリサイザ", style=wx.FRAME_NO_TASKBAR | wx.FRAME_TOOL_WINDOW | wx.STAY_ON_TOP)
        self.frame.SetMinClientSize((380, 297))
        self.frame.SetClientSize((380, 297))
        layout.PopupPanel.__init__(self, self.frame)
        self.frame.Layout()
        self.frame.SetTitle("ReplayResizer")
        self.frame.SetIcon(icon.GetIcon())

        self._shown_popup = False
        self._in_cursor = False
        self.pressed_shift = False
        self.action_count_lefts = -1

        self.move_frame_position()
        self.draw_entry(None)

        self.thumbnail.SetDropTarget(FileDropTarget(self.on_drop_files))
        self.thumbnail.Bind(wx.EVT_LEFT_DOWN, self.on_thumbnail_drag)
        self.thumbnail.Bind(wx.EVT_LEFT_DCLICK, self.on_thumbnail_open)
        self.app.app.Bind(wx.EVT_MOTION, self.on_mouse)

    @property
    def current_entry(self):
        return self.app.current_entry

    #

    def draw_entry(self, entry: Optional[ResizeEntry]):
        if self._shown_popup:
            log.debug("draw entry (cancelled by shown-popup)")
            return

        self.Freeze()
        log.debug("draw entry")

        try:
            try:
                self.update_buttons()
            except (Exception,):
                log.exception("exception in update_buttons (by update_entry) (ignored)")

            if not entry:
                progress = 0
            elif entry.is_encoding:
                progress = min(100, max(0, int(round(entry.encode_progress * 100))))
            elif entry.completed:
                progress = 100
            else:
                progress = 0

            self.gauge.SetValue(progress)

            from replayresizer.replayresizer import FRAME_TITLE

            if entry is None:
                self.title.SetLabel(FRAME_TITLE)
                size = self.thumbnail.GetSize()

                bitmap = wx.Bitmap(width=size[0], height=size[1])

                if Path(self.app.app_directory / "wallpaper.png").is_file():
                    try:
                        img = wx.Image(str(self.app.app_directory / "wallpaper.png"))
                        img = img.Scale(*size)  # type: wx.Image
                        bitmap = img.ConvertToBitmap()

                    except (Exception,):
                        log.warning("Failed to loading wallpaper", exc_info=True)

                self.thumbnail.SetBitmap(bitmap)
                self.Refresh()
                self.Layout()
                return

            if entry.media_info:
                bit_rate = entry.media_info.bit_rate
                frames = entry.media_info.frame_rate

                title = FRAME_TITLE + "  -  "
                if bit_rate:
                    title += get_bit_rate_label(bit_rate) + " "

                w, h = entry.media_info.scale_wh
                title += f"{w}x{h} "

                if frames:
                    title += f"{frames}fps "

                m, s = divmod(entry.media_info.duration, 60)
                title += f"[{int(m)}:{int(s):02}]"
                self.title.SetLabel(title)

            if entry.thumbnail_cache:
                bitmap = wx.Bitmap(entry.thumbnail_cache)
                self.thumbnail.SetBitmap(bitmap)
            else:
                size = self.thumbnail.GetSize()
                bitmap = wx.Bitmap(width=size[0], height=size[1])
                self.thumbnail.SetBitmap(bitmap)

            dc = wx.MemoryDC()
            dc.SelectObject(bitmap)
            gc = wx.GraphicsContext.Create(dc)  # type: wx.GraphicsContext

            self._draw_file_size(gc, entry)

            if entry.size_adjust != entry.size_adjust_first:
                self._draw_retry_info(gc, entry)

            if self.config.draw_media_info:
                self._draw_media_info(gc, entry)

            self.thumbnail.SetBitmap(bitmap)
            self.Refresh()
            self.Layout()
            del gc
            del dc
        finally:
            self.Thaw()

    def async_draw_message(self, entry: Optional[ResizeEntry], message: PopupMessage):
        wx.CallAfter(self.draw_message, entry=entry, message=message)

    def draw_message(self, entry: Optional[ResizeEntry], message: PopupMessage):
        self.Freeze()
        log.debug("draw message")
        try:
            if entry and entry.thumbnail_cache:
                bitmap = wx.Bitmap(entry.thumbnail_cache)
            else:
                size = self.thumbnail.GetSize()
                bitmap = wx.Bitmap(width=size[0], height=size[1])

            dc = wx.MemoryDC()
            dc.SelectObject(bitmap)
            gc = wx.GraphicsContext.Create(dc)  # type: wx.GraphicsContext

            self._draw_popup_message(gc, message)

            self.thumbnail.SetBitmap(bitmap)
            self.Refresh()
            self.Layout()
            del gc
            del dc
            self._shown_popup = True

        finally:
            self.Thaw()
            self.frame.Show()

    def hide_message_flag(self):
        self._shown_popup = False

    def _draw_file_size(self, gc: wx.GraphicsContext, entry: ResizeEntry):
        width, height = self.thumbnail.GetSize()

        if not entry:
            return
        elif entry.is_encoding:
            progress = min(100, max(0, int(round(entry.encode_progress * 100))))
            line1 = f"{get_file_size_label(entry.resized_size)}  /  {progress}%"
            over_limit = entry.resized_size > self.config.size_limit
        elif entry.resized and entry.resized_size:
            line1 = get_file_size_label(entry.resized_size)
            over_limit = entry.resized_size > self.config.size_limit
        elif entry.source_size <= entry.size_limit:
            line1 = get_file_size_label(entry.source_size)
            over_limit = entry.source_size > self.config.size_limit
        else:
            return

        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)  # type: wx.Font
        font.SetPixelSize(wx.Size(0, 14))
        gc.SetFont(font, wx.Colour(60, 60, 60, 255))
        gc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 140)))

        text_width, text_height, descent, _ = gc.GetFullTextExtent(line1)

        gc.DrawRectangle(
            width - text_width - (descent * 2) - 1,
            height - text_height - (descent * 2) - 1,
            text_width + descent * 2 + 1,
            text_height + descent * 2 + 1
        )
        gc.DrawText(line1, width - text_width - descent + 1, height - text_height - descent + 1)
        gc.SetFont(font, wx.Colour(255, 0, 0) if over_limit else wx.Colour(255, 255, 255, 255))
        gc.DrawText(line1, width - text_width - descent, height - text_height - descent)

    def _draw_retry_info(self, gc: wx.GraphicsContext, entry: ResizeEntry):
        width, height = self.thumbnail.GetSize()

        if not entry:
            return

        line = f"Retry: {round(entry.size_adjust_first, 1)}% -> {round(entry.size_adjust, 1)}%"

        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)  # type: wx.Font
        font.SetPixelSize(wx.Size(0, 14))
        gc.SetFont(font, wx.Colour(60, 60, 60, 255))
        gc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 140)))

        text_width, text_height, descent, _ = gc.GetFullTextExtent(line)

        gc.DrawRectangle(
            0,
            height - text_height - (descent * 2) - 1,
            text_width + descent * 2 + 1,
            text_height + descent * 2 + 1
        )
        gc.DrawText(line, descent + 1, height - text_height - descent - 1)
        gc.SetFont(font, wx.Colour(255, 0, 0))
        gc.DrawText(line, descent, height - text_height - descent)

    def _draw_media_info(self, gc: wx.GraphicsContext, entry: ResizeEntry):
        size_resized = scale_orig = scale_resized = bit_rate_orig = bit_rate_resized = ""
        frames_orig = frames_resized = codec_orig = codec_resized = gain_orig = gain_resized = ""
        size_orig = get_file_size_label(entry.source_size)
        filename = entry.source.name

        if entry.resized_size:
            size_resized = get_file_size_label(entry.resized_size)

            if entry.is_encoding:
                progress = min(100, max(0, int(round(entry.encode_progress * 100)))) if entry.encode_progress else 0
                size_resized += f" ({progress}%)"

        if entry.media_info:
            w, h = entry.media_info.scale_wh
            scale_orig = f"{w}x{h}"
            scale_resized = f"{entry.width}x{entry.height}" if entry.width or entry.height else ""
            if entry.media_info.bit_rate:
                bit_rate_orig = get_bit_rate_label(entry.media_info.bit_rate)
            bit_rate_resized = get_bit_rate_label(entry.bit_rate) if entry.bit_rate else ""
            frames_orig = entry.media_info.frame_rate
            frames_orig = f"{round(frames_orig, 1)} fps" if frames_orig else ""
            frames_resized = entry.frames
            frames_resized = f"{round(frames_resized, 1)} fps" if frames_resized else ""
            codec_orig = get_codec_name(entry.media_info.codec_name)
            codec_resized = entry.preset_name
            gain_orig = entry.media_info.peak_gain
            gain_orig = f"{round(gain_orig, 1)} dB" if gain_orig is not None else ""
            gain_resized = entry.fix_gain
            gain_resized = f"{' +'[gain_resized > 0].strip()}{round(gain_resized, 1)} dB" if gain_resized else ""

        lines = [f"{key:8}: {orig:10} > {resized}"
                 for key, orig, resized in [
                     ("Size", size_orig, size_resized),
                     ("Scale", scale_orig, scale_resized),
                     ("FPS", frames_orig, frames_resized),
                     ("Codec", codec_orig, codec_resized),
                     ("Bitrate", bit_rate_orig, bit_rate_resized),
                 ]]
        if self.config.normalized_volume:
            lines.append(f"PeakGain: {gain_orig:10} > {gain_resized}")

        lines.insert(0, filename)
        lines.insert(1, "")

        text = "\n".join(lines)
        # font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)  # type: wx.Font
        font = wx.Font(wx.FontInfo(10).Family(wx.FONTFAMILY_SCRIPT).FaceName("MS Gothic"))

        gc.SetFont(font, wx.Colour(60, 60, 60, 255))
        gc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 140)))

        text_width, text_height, descent, _ = gc.GetFullTextExtent(text)

        gc.DrawRectangle(0, 0, text_width + descent * 4 + 1, text_height + descent * 4 + 1)
        gc.DrawText(text, descent * 2 + 1, descent * 2 + 1)
        gc.SetFont(font, wx.Colour(255, 255, 255, 255))
        gc.DrawText(text, descent * 2, descent * 2)

        pass

    def _draw_popup_message(self, gc: wx.GraphicsContext, msg: PopupMessage):
        width, height = self.thumbnail.GetSize()

        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)  # type: wx.Font
        font.SetPixelSize(wx.Size(0, 16))
        gc.SetFont(font, wx.Colour(60, 60, 60, 255))
        # gc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 140)))
        gc.SetBrush(wx.Brush(wx.Colour(160, 50, 50, 200)))

        text_width, text_height, descent, _ = gc.GetFullTextExtent(msg.title)
        if msg.content:
            y = descent
        else:
            y = descent + 30

        x = width / 2 - text_width / 2

        # gc.DrawRectangle(x - descent, y - descent, text_width + descent * 2, text_height + descent * 2)
        gc.DrawRectangle(0, y - descent, width, text_height + descent * 2)
        gc.DrawText(msg.title, x + 1, y + 1)
        gc.SetFont(font, wx.Colour(255, 255, 255, 255))
        gc.DrawText(msg.title, x, y)
        y += text_height + descent

        if msg.description:
            font.SetPixelSize(wx.Size(0, 14))
            gc.SetFont(font, wx.Colour(60, 60, 60, 255))
            text_width, text_height, descent, _ = gc.GetFullTextExtent(msg.description)
            x = width / 2 - text_width / 2
            gc.DrawRectangle(0, y, width, text_height + descent * 2)
            y += descent
            gc.DrawText(msg.description, x + 1, y + 1)
            gc.SetFont(font, wx.Colour(255, 255, 255, 255))
            gc.DrawText(msg.description, x, y)
            y += text_height + descent

        if msg.content:
            gc.SetBrush(wx.Brush(wx.Colour(20, 20, 20, 160)))
            gc.DrawRectangle(0, y, width, height)

            font = wx.Font(wx.FontInfo(8).Family(wx.FONTFAMILY_SCRIPT).FaceName("MS Gothic"))
            gc.SetFont(font, wx.Colour(255, 255, 255, 255))
            _, _, descent, _ = gc.GetFullTextExtent("SAMPLE")

            y += descent
            space = height - y

            lines = msg.content.splitlines()
            _, text_height, _, _ = gc.GetFullTextExtent("\n".join(lines))
            while lines and space < text_height:
                lines.pop(0)
                text_width, text_height, descent, _ = gc.GetFullTextExtent("\n".join(lines))

            if not lines:
                return

            gc.DrawText("\n".join(lines), 8, y + 8)

    #

    def move_frame_position(self):
        display = wx.Display()
        _, _, x, y = display.GetClientArea()
        w, h = self.frame.GetClientSize()
        x -= 8 + w
        y -= 8 + h

        self.frame.SetPosition((x, y))

    def on_button(self, event):
        event.Skip()

        if event.GetEventObject() is self.button_done:
            self.action_count_lefts = -1
            self.app.call_close_action(shift=self.pressed_shift)

        elif event.GetEventObject() is self.button_action:
            if self.current_entry and self.current_entry.is_encoding:
                self.app.skip_current_entry()
            # self.frame.Hide()
            pass

    def on_thumbnail_drag(self, _):
        entry = self.current_entry

        if not entry or not entry.complete_file:
            return

        obj = wx.FileDataObject()
        obj.AddFile(str(entry.complete_file))

        source = wx.DropSource(self.thumbnail)
        source.SetData(obj)
        source.DoDragDrop(True)

        if self.config.auto_close_when_enum == AutoActionWhen.ON_DRAGGED:
            self.start_action_timer()

    def on_thumbnail_open(self, _):
        entry = self.current_entry

        if not entry or not entry.complete_file:
            return

        open_explorer(entry.complete_file, select=True)

    def on_drop_files(self, x, y, files):
        current_resize = None
        if self.current_entry and self.current_entry.resized:
            current_resize = self.current_entry.resized.resolve()

        for file in files:
            file = Path(file).resolve()
            if file.is_file():
                if file != current_resize:
                    self.app.on_recorded(file)
                    return True
        return False

    def on_key_press(self, key):
        if key != Key.shift:
            return

        if not self.pressed_shift:
            self.pressed_shift = True

            if self.frame.IsShown():
                self.update_buttons()

    def on_key_release(self, key):
        if key != Key.shift:
            return

        if self.pressed_shift:
            self.pressed_shift = False

            if self.frame.IsShown():
                self.update_buttons()

    def on_mouse(self, event: wx.MouseEvent):
        event.Skip()

        if event.GetEventObject().GetTopLevelParent() is self.frame:
            if not self._in_cursor:
                self._in_cursor = True
                if self.action_count_lefts >= 0:
                    self.action_count_lefts = -1
                self.update_buttons()

    #

    def start_action_timer(self):
        if self.config.auto_close_delay <= 0:
            return

        self.action_count_lefts = self.config.auto_close_delay
        self.update_buttons()
        self._in_cursor = False
        wx.CallLater(1000, self._on_action_time).Start()

    def _on_action_time(self):
        self.action_count_lefts -= 1

        if self.action_count_lefts > 0:
            self.update_buttons()

            wx.CallLater(1000, self._on_action_time).Start()

        elif self.action_count_lefts == 0:
            self.app.call_close_action()

        else:
            pass

    def update_buttons(self):
        e = self.current_entry

        if not self.current_entry:
            self.button_done.SetLabel("閉じる")
            self.button_action.Hide()

        elif self.current_entry.is_encoding:
            self.button_action.SetLabel("スキップ")
            self.button_action.Show()
            self.button_done.SetLabel("閉じる")

        elif not self.current_entry.completed:
            self.button_done.SetLabel("閉じる")
            self.button_action.Hide()

        else:  # completed
            action = self.config.close_action_enum if not self.pressed_shift else self.config.close_action_shift_enum

            delete_resize = action == CloseAction.CLOSE_AND_DELETE_RESIZE or action == CloseAction.CLOSE_AND_DELETE_ALL
            delete_source = action == CloseAction.CLOSE_AND_DELETE_SOURCE or action == CloseAction.CLOSE_AND_DELETE_ALL
            if e.order_options & OrderOption.DELETE_SOURCE_WHEN_COMPLETE:
                delete_source = True

            line2 = ""
            if not delete_resize and not delete_source:
                line1 = "閉じる"
            elif delete_resize and delete_source:
                line1 = "閉じる"
                line2 = "(削除: 元ファイルとリサイズファイル)"
            elif not delete_resize and delete_source:
                line1 = "閉じる"
                line2 = "(削除: 元ファイル)"
            elif delete_resize and not delete_source:
                line1 = "閉じる"
                line2 = "(削除: リサイズファイル)"
            else:
                line1 = action.name

            if self.action_count_lefts >= 0 and not self.pressed_shift:
                line1 += f" ({self.action_count_lefts})"

            self.button_done.SetLabel(f"{line1}\n{line2}" if line2 else line1)
            self.button_action.Hide()

        self.sizer_buttons.Layout()
