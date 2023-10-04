import json
import re
from enum import Enum
from pathlib import Path
from typing import List
from typing import Pattern

from replayresizer.tools import color16_to_colour, colour_to_color16


def parse_int(value: str):
    try:
        return int(value)
    except ValueError:
        return 0


class CloseAction(Enum):
    CLOSE = 0
    CLOSE_AND_DELETE_SOURCE = 1
    CLOSE_AND_DELETE_RESIZE = 2
    CLOSE_AND_DELETE_ALL = 3


class AutoActionWhen(Enum):
    ON_COMPLETED = 0
    ON_DRAGGED = 1


class AppConfiguration(object):
    def __init__(self, path: Path):
        self._path = path
        # shadow
        self.setup = True
        self.first_start = True
        self.pause = False
        self.rename_format = "{name}_resized.{ext}"
        # generic
        self.input_directory = ""
        self.output_directory = ""
        self.ffmpeg_command = "ffmpeg"
        self.ffprobe_command = "ffprobe"
        self.listen_delay = 0
        self.color = 0x592e31
        self.thumbnail = True
        self.draw_media_info = False
        self.silent_popup = False
        self.ignore_error = False
        self.close_action = 2
        self.close_action_with_shift = 0
        self.auto_close_delay = 5
        self.auto_close_when = 0
        # encode
        self.size_limit = 24950
        self.hq_bitrate = 1200
        self.ulq_bitrate = 260
        self.normalized_volume = True
        self.volume_db = 2.0
        self.volume_normalize_limit_db = 20.0
        #   HQ
        self.hq_fps30 = True
        self.hq_no_audio = False
        self.hq_width = 1280
        self.hq_height = 0
        self.hq_size_adjust = 100.0
        self.hq_encoder_params = "-deadline realtime -cpu-used -8"
        #   LQ
        self.lq_fps30 = True
        self.lq_no_audio = False
        self.lq_width = 640
        self.lq_height = 0
        self.lq_size_adjust = 96.0
        self.lq_encoder_params = "-preset veryfast"
        #   ULQ
        self.ulq_fps16 = True
        self.ulq_no_audio = False
        self.ulq_width = 320
        self.ulq_height = 0
        self.ulq_size_adjust = 96.0
        self.ulq_encoder_params = "-preset veryfast"
        # target files
        self.targets = ["1:\\.mp4$"]
        self.ignores = ["1:^\\."]

        # cached
        self._active_targets = []  # type: List[Pattern]
        self._active_ignores = []  # type: List[Pattern]
        self.compile_targets()

    def load_from_panel(self, panel):
        """
        :type panel: replayresizer.settings_panel.SettingsFrame
        """
        self.input_directory = str(panel.tc_dir_input.GetValue())
        self.output_directory = str(panel.tc_dir_output.GetValue())
        self.ffmpeg_command = str(panel.tc_ffmpeg.GetValue())
        self.ffprobe_command = str(panel.tc_ffprobe.GetValue())
        self.listen_delay = int(panel.spin_listen_delay.GetValue())
        self.color = colour_to_color16(panel.btn_my_color.GetColour())
        self.thumbnail = bool(panel.check_thumbnail.GetValue())
        self.draw_media_info = bool(panel.check_draw_media_info.GetValue())
        self.silent_popup = bool(panel.check_silent_popup.GetValue())
        self.ignore_error = bool(panel.check_ignore_error.GetValue())
        self.close_action = int(panel.choice_close_action.GetSelection())
        self.close_action_with_shift = int(panel.choice_close_action_with_shift.GetSelection())
        self.auto_close_delay = int(panel.spin_auto_close_delay.GetValue())
        self.auto_close_when = int(panel.choice_auto_close_when.GetSelection())
        self.size_limit = int(panel.spin_size_limit.GetValue())
        self.hq_fps30 = bool(panel.check_hq_fps30.GetValue())
        self.hq_no_audio = bool(panel.check_hq_no_audio.GetValue())
        self.hq_width = parse_int(panel.tc_hq_scale_width.GetValue())
        self.hq_height = parse_int(panel.tc_hq_scale_height.GetValue())
        self.hq_size_adjust = float(panel.spin_hq_size_adjust.GetValue())
        self.hq_encoder_params = str(panel.tc_hq_encoder_params.GetValue())
        self.lq_fps30 = bool(panel.check_lq_fps30.GetValue())
        self.lq_no_audio = bool(panel.check_lq_no_audio.GetValue())
        self.lq_width = parse_int(panel.tc_lq_scale_width.GetValue())
        self.lq_height = parse_int(panel.tc_lq_scale_height.GetValue())
        self.lq_size_adjust = float(panel.spin_lq_size_adjust.GetValue())
        self.lq_encoder_params = str(panel.tc_lq_encoder_params.GetValue())
        self.ulq_fps16 = bool(panel.check_ulq_fps16.GetValue())
        self.ulq_no_audio = bool(panel.check_ulq_no_audio.GetValue())
        self.ulq_width = parse_int(panel.tc_ulq_scale_width.GetValue())
        self.ulq_height = parse_int(panel.tc_ulq_scale_height.GetValue())
        self.ulq_size_adjust = float(panel.spin_ulq_size_adjust.GetValue())
        self.ulq_encoder_params = str(panel.tc_ulq_encoder_params.GetValue())
        self.hq_bitrate = parse_int(panel.tc_hq_bitrate.GetValue()) or 1200
        self.ulq_bitrate = parse_int(panel.tc_ulq_bitrate.GetValue()) or 260
        self.normalized_volume = bool(panel.check_normalized_volume.GetValue())
        self.volume_db = float(panel.spin_volume_db.GetValue())
        self.volume_normalize_limit_db = float(panel.spin_volume_normalize_limit_db.GetValue())
        self.targets = [f"{int(panel.list_target.IsChecked(idx))}:{entry}"
                        for idx, entry in enumerate(panel.list_target.GetItems())]
        self.ignores = [f"{int(panel.list_ignore.IsChecked(idx))}:{entry}"
                        for idx, entry in enumerate(panel.list_ignore.GetItems())]
        self.compile_targets()

    def load_to_panel(self, panel):
        """
        :type panel: replayresizer.settings_panel.SettingsFrame
        """
        panel.tc_dir_input.SetValue(str(self.input_directory or ""))
        panel.tc_dir_output.SetValue(str(self.output_directory or ""))
        panel.tc_ffmpeg.SetValue(str(self.ffmpeg_command or ""))
        panel.tc_ffprobe.SetValue(str(self.ffprobe_command or ""))
        panel.spin_listen_delay.SetValue(max(0, int(self.listen_delay or 0)))
        panel.btn_my_color.SetColour(color16_to_colour(int(self.color or 0)))
        panel.check_thumbnail.SetValue(bool(self.thumbnail or False))
        panel.check_draw_media_info.SetValue(bool(self.draw_media_info or False))
        panel.check_silent_popup.SetValue(bool(self.silent_popup or False))
        panel.check_ignore_error.SetValue(bool(self.ignore_error or False))
        panel.choice_close_action.Select(max(0, min(4, int(self.close_action or 0))))
        panel.choice_close_action_with_shift.Select(max(0, min(4, int(self.close_action_with_shift or 0))))
        panel.spin_auto_close_delay.SetValue(max(0, int(self.auto_close_delay or 0)))
        panel.choice_auto_close_when.Select(max(0, min(1, int(self.auto_close_when or 0))))
        panel.spin_size_limit.SetValue(max(200, min(99999999, int(self.size_limit or 0))))
        panel.check_hq_fps30.SetValue(bool(self.hq_fps30 or False))
        panel.check_hq_no_audio.SetValue(bool(self.hq_no_audio or False))
        panel.tc_hq_scale_width.SetValue(str(max(0, int(self.hq_width or 0))))
        panel.tc_hq_scale_height.SetValue(str(max(0, int(self.hq_height or 0))))
        panel.spin_hq_size_adjust.SetValue(float(self.hq_size_adjust or 0))
        panel.tc_hq_encoder_params.SetValue(str(self.hq_encoder_params or ""))
        panel.check_lq_fps30.SetValue(bool(self.lq_fps30 or False))
        panel.check_lq_no_audio.SetValue(bool(self.lq_no_audio or False))
        panel.tc_lq_scale_width.SetValue(str(max(0, int(self.lq_width or 0))))
        panel.tc_lq_scale_height.SetValue(str(max(0, int(self.lq_height or 0))))
        panel.spin_lq_size_adjust.SetValue(float(self.lq_size_adjust or 0))
        panel.tc_lq_encoder_params.SetValue(str(self.lq_encoder_params or ""))
        panel.check_ulq_fps16.SetValue(bool(self.ulq_fps16 or False))
        panel.check_ulq_no_audio.SetValue(bool(self.ulq_no_audio or False))
        panel.tc_ulq_scale_width.SetValue(str(max(0, int(self.ulq_width or 0))))
        panel.tc_ulq_scale_height.SetValue(str(max(0, int(self.ulq_height or 0))))
        panel.spin_ulq_size_adjust.SetValue(float(self.ulq_size_adjust or 0))
        panel.tc_ulq_encoder_params.SetValue(str(self.ulq_encoder_params or ""))
        panel.tc_hq_bitrate.SetValue(str(int(self.hq_bitrate or 1200)))
        panel.tc_ulq_bitrate.SetValue(str(int(self.ulq_bitrate or 260)))
        panel.check_normalized_volume.SetValue(bool(self.normalized_volume or False))
        panel.spin_volume_db.SetValue(float(self.volume_db or 0))
        panel.spin_volume_normalize_limit_db.SetValue(float(self.volume_normalize_limit_db or 0))
        panel.tc_target_value.SetValue("")
        panel.list_target.Clear()
        for entry in self.targets:
            index = panel.list_target.Append(entry[2:])
            if entry.startswith("1:"):
                panel.list_target.Check(index)
        panel.tc_ignore_value.SetValue("")
        panel.list_ignore.Clear()
        for entry in self.ignores:
            index = panel.list_ignore.Append(entry[2:])
            if entry.startswith("1:"):
                panel.list_ignore.Check(index)

    def load_from_json_file(self, *, save_default=True):
        if not self._path.is_file():
            if save_default:
                self.save_to_json_file()
            return

        with self._path.open(encoding="utf-8") as file:
            data = json.load(file)

        for key, value in self.__dict__.items():
            if key.startswith("_") or key not in data:
                continue

            setattr(self, key, data.get(key))

    def save_to_json_file(self):
        Path(self._path.parent).mkdir(parents=True, exist_ok=True)

        if self._path.exists():
            with self._path.open(encoding="utf-8") as file:
                data = json.load(file)
        else:
            data = {}

        for key, value in self.__dict__.items():
            if key.startswith("_"):
                continue

            data[key] = value

        with self._path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    @property
    def active_targets(self) -> List[Pattern]:
        return self._active_targets

    @property
    def active_ignores(self) -> List[Pattern]:
        return self._active_ignores

    @property
    def close_action_enum(self):
        try:
            return CloseAction(self.close_action)
        except ValueError:
            return CloseAction.CLOSE

    @property
    def close_action_shift_enum(self):
        try:
            return CloseAction(self.close_action_with_shift)
        except ValueError:
            return CloseAction.CLOSE

    @property
    def auto_close_when_enum(self):
        try:
            return AutoActionWhen(self.auto_close_when)
        except ValueError:
            return AutoActionWhen.ON_COMPLETED

    #

    def compile_targets(self):
        self._active_targets = [re.compile(entry[2:]) for entry in self.targets if entry.startswith("1:")]
        self._active_ignores = [re.compile(entry[2:]) for entry in self.ignores if entry.startswith("1:")]
