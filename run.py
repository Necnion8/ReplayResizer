import os
import sys
from pathlib import Path


if __name__ == '__main__':
    app_dir = Path(sys.argv[0]).parent
    os.chdir(app_dir)

    import wx

    app = wx.App()

    instance = wx.SingleInstanceChecker("ReplayResizer-" + wx.GetUserId())

    if instance.IsAnotherRunning():
        wx.MessageDialog(None, "すでに起動しています。", caption="リプレイリサイザ", style=wx.OK).ShowModal()
        wx.Exit()

    from replayresizer.replayresizer import ReplayResizer

    main = ReplayResizer(app, app_directory=app_dir)
    main.setup_logging()
    main.launch(sys.argv[1:])
    app.MainLoop()
