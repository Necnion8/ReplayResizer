import wx

from replayresizer import layout
from replayresizer.images import icon
from replayresizer.config import AppConfiguration


class SettingsFrame(layout.SettingsPanel):
    def __init__(self, parent, config: AppConfiguration):
        layout.SettingsPanel.__init__(self, parent)
        from replayresizer.replayresizer import FRAME_TITLE, VERSION
        self.SetTitle(f"設定  -  {FRAME_TITLE} v{VERSION}")
        self.SetIcon(icon.GetIcon())
        self.config = config

        self.list_target.Bind(wx.EVT_LISTBOX, self.on_select)
        self.list_ignore.Bind(wx.EVT_LISTBOX, self.on_select)
        self.config.load_to_panel(self)
        self.result = False
        self._before_input = config.input_directory
        self._before_ffmpeg = config.ffmpeg_command
        self._before_ffprobe = config.ffprobe_command

    def on_button(self, event: wx.CommandEvent):
        if event.GetEventObject() is self.btn_close:
            self.result = True

            self.config.load_from_panel(self)
            try:
                self.config.save_to_json_file()
            finally:
                self.Close()

        elif event.GetEventObject() is self.btn_cancel:
            self.Close()

        elif event.GetEventObject() is self.btn_dir_input:
            default = self.tc_dir_input.GetValue() or wx.EmptyString
            dialog = wx.DirDialog(self, defaultPath=default, style=wx.DD_DIR_MUST_EXIST | wx.DD_CHANGE_DIR)

            if dialog.ShowModal() == wx.ID_OK:
                value = str(dialog.GetPath())
                self.config.input_directory = value
                self.tc_dir_input.ChangeValue(value)

            dialog.Destroy()

        elif event.GetEventObject() is self.btn_dir_output:
            default = self.tc_dir_output.GetValue() or wx.EmptyString
            dialog = wx.DirDialog(self, defaultPath=default, style=wx.DD_DIR_MUST_EXIST | wx.DD_CHANGE_DIR)

            if dialog.ShowModal() == wx.ID_OK:
                value = str(dialog.GetPath())
                self.config.output_directory = value
                self.tc_dir_output.ChangeValue(value)

            dialog.Destroy()

        elif event.GetEventObject() is self.btn_ffmpeg:
            default = self.tc_ffmpeg.GetValue() or wx.EmptyString
            dialog = wx.FileDialog(self, defaultFile=default, style=wx.FD_FILE_MUST_EXIST | wx.FD_CHANGE_DIR)

            if dialog.ShowModal() == wx.ID_OK:
                value = str(dialog.GetPath())
                self.config.ffmpeg_command = value
                self.tc_ffmpeg.ChangeValue(value)

            dialog.Destroy()

        elif event.GetEventObject() is self.btn_ffprobe:
            default = self.tc_ffprobe.GetValue() or wx.EmptyString
            dialog = wx.FileDialog(self, defaultFile=default, style=wx.FD_FILE_MUST_EXIST | wx.FD_CHANGE_DIR)

            if dialog.ShowModal() == wx.ID_OK:
                value = str(dialog.GetPath())
                self.config.ffprobe_command = value
                self.tc_ffprobe.ChangeValue(value)

            dialog.Destroy()

        elif event.GetEventObject() is self.btn_target_add:
            if self.tc_target_value.GetValue():
                index = self.list_target.Append(self.tc_target_value.GetValue())
                self.list_target.Check(index)
                self.list_target.Select(index)

        elif event.GetEventObject() is self.btn_target_remove:
            index = self.list_target.GetSelection()
            if index != -1:
                self.list_target.Delete(index)
                self.list_target.Select(-1)
                self.tc_target_value.ChangeValue("")

        elif event.GetEventObject() is self.btn_ignore_add:
            if self.tc_ignore_value.GetValue():
                index = self.list_ignore.Append(self.tc_ignore_value.GetValue())
                self.list_ignore.Check(index)
                self.list_ignore.Select(index)

        elif event.GetEventObject() is self.btn_ignore_remove:
            index = self.list_ignore.GetSelection()
            if index != -1:
                self.list_ignore.Delete(index)
                self.list_ignore.Select(-1)
                self.tc_ignore_value.ChangeValue("")

    def on_text(self, event: wx.CommandEvent):
        if event.GetEventObject() is self.tc_target_value and self.tc_target_value.GetValue():
            index = self.list_target.GetSelection()
            if index != -1:
                check = self.list_target.IsChecked(index)
                self.list_target.Delete(index)
                self.list_target.Insert(self.tc_target_value.GetValue(), index)
                self.list_target.Check(index, check)
                self.list_target.Select(index)

        elif event.GetEventObject() is self.tc_ignore_value and self.tc_ignore_value.GetValue():
            index = self.list_ignore.GetSelection()
            if index != -1:
                check = self.list_ignore.IsChecked(index)
                self.list_ignore.Delete(index)
                self.list_ignore.Insert(self.tc_ignore_value.GetValue(), index)
                self.list_ignore.Check(index, check)
                self.list_ignore.Select(index)

        elif event.GetEventObject() is self.tc_hq_bitrate:
            value: str = self.tc_hq_bitrate.GetValue()
            try:
                if 0 >= int(value):
                    raise ValueError
            except ValueError:
                self.tc_hq_bitrate.SetBackgroundColour(wx.RED)
            else:
                self.tc_hq_bitrate.SetBackgroundColour(wx.NullColour)
            self.tc_hq_bitrate.Refresh()

        elif event.GetEventObject() is self.tc_ulq_bitrate:
            value = self.tc_ulq_bitrate.GetValue()
            try:
                if 0 >= int(value):
                    raise ValueError
            except ValueError:
                self.tc_ulq_bitrate.SetBackgroundColour(wx.RED)
            else:
                self.tc_ulq_bitrate.SetBackgroundColour(wx.NullColour)
            self.tc_ulq_bitrate.Refresh()

        elif event.GetEventObject() is self.tc_hq_scale_width:
            value = self.tc_hq_scale_width.GetValue()
            try:
                if 0 > int(value):
                    raise ValueError
            except ValueError:
                self.tc_hq_scale_width.SetBackgroundColour(wx.RED)
            else:
                self.tc_hq_scale_width.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DFACE))
            self.tc_hq_scale_width.Refresh()

        elif event.GetEventObject() is self.tc_hq_scale_height:
            value = self.tc_hq_scale_height.GetValue()
            try:
                if 0 > int(value):
                    raise ValueError
            except ValueError:
                self.tc_hq_scale_height.SetBackgroundColour(wx.RED)
            else:
                self.tc_hq_scale_height.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DFACE))
            self.tc_hq_scale_height.Refresh()

        elif event.GetEventObject() is self.tc_lq_scale_width:
            value = self.tc_lq_scale_width.GetValue()
            try:
                if 0 > int(value):
                    raise ValueError
            except ValueError:
                self.tc_lq_scale_width.SetBackgroundColour(wx.RED)
            else:
                self.tc_lq_scale_width.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DFACE))
            self.tc_lq_scale_width.Refresh()

        elif event.GetEventObject() is self.tc_lq_scale_height:
            value = self.tc_lq_scale_height.GetValue()
            try:
                if 0 > int(value):
                    raise ValueError
            except ValueError:
                self.tc_lq_scale_height.SetBackgroundColour(wx.RED)
            else:
                self.tc_lq_scale_height.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DFACE))
            self.tc_lq_scale_height.Refresh()

        elif event.GetEventObject() is self.tc_ulq_scale_width:
            value = self.tc_ulq_scale_width.GetValue()
            try:
                if 0 > int(value):
                    raise ValueError
            except ValueError:
                self.tc_ulq_scale_width.SetBackgroundColour(wx.RED)
            else:
                self.tc_ulq_scale_width.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DFACE))
            self.tc_ulq_scale_width.Refresh()

        elif event.GetEventObject() is self.tc_ulq_scale_height:
            value = self.tc_ulq_scale_height.GetValue()
            try:
                if 0 > int(value):
                    raise ValueError
            except ValueError:
                self.tc_ulq_scale_height.SetBackgroundColour(wx.RED)
            else:
                self.tc_ulq_scale_height.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DFACE))
            self.tc_ulq_scale_height.Refresh()

    def on_check(self, event):
        pass

    def on_select(self, event: wx.CommandEvent):
        if event.GetEventObject() is self.list_target:
            index = self.list_target.GetSelection()
            value = self.list_target.GetString(index)
            self.tc_target_value.ChangeValue(value)

        elif event.GetEventObject() is self.list_ignore:
            index = self.list_ignore.GetSelection()
            value = self.list_ignore.GetString(index)
            self.tc_ignore_value.ChangeValue(value)

    @property
    def changed_input(self):
        return self.tc_dir_input.GetValue() != self._before_input

    @property
    def changed_ffmpeg_ffprobe(self):
        return self.tc_ffmpeg.GetValue() != self._before_ffmpeg or self.tc_ffprobe.GetValue() != self._before_ffprobe

