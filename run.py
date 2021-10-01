import os
import sys
from pathlib import Path


if __name__ == '__main__':
    os.chdir(Path(sys.argv[0]).parent)

    import wx

    app = wx.App()

    instance = wx.SingleInstanceChecker("ReplayResizer-" + wx.GetUserId())

    if instance.IsAnotherRunning():
        wx.MessageDialog(None, "すでに起動しています。", caption="リプレイリサイザ", style=wx.OK).ShowModal()
        wx.Exit()

    from replayresizer.replayresizer import ReplayResizer

    main = ReplayResizer(app)
    main.setup_logging()
    main.launch(sys.argv[1:])
    app.MainLoop()
