import wx
import wx.adv

from replayresizer import images


class TaskBar(wx.adv.TaskBarIcon):
    def __init__(self):
        wx.adv.TaskBarIcon.__init__(self)
        from replayresizer.replayresizer import FRAME_TITLE
        self.title = FRAME_TITLE
        self._icon = images.icon.GetIcon()  # type: wx.Icon
        self._icon_running = images.icon_running.GetBitmap()  # type: wx.Bitmap

        # self._icon_running = wx.Image("icon_test.png").ConvertToBitmap()

        pass

    def show(self, *, progress: int = None):
        if progress is None:
            self.SetIcon(self._icon, self.title)
            return

        progress = max(0, min(100, progress))

        bmp = wx.Bitmap(self._icon_running)
        dc = wx.MemoryDC()
        dc.SelectObject(bmp)
        gc = wx.GraphicsContext.Create(dc)  # type: wx.GraphicsContext
        gc.SetBrush(wx.Brush(wx.Colour(255, 200, 0, 200)))

        width = 8
        size = 64
        total = (size - width) * 4
        current = round(progress / 100 * total)
        # print(f"total={total} current={current} progress={progress}%")
        # 32 + 64 + 64 + 64 + 32

        # top right
        x = size / 2
        y = 0
        bar = round(size / 2)
        length = max(0, min(current, bar))
        gc.DrawRectangle(x, y, length, width)
        # print(f"TopR  {x}, {y}, len={length} current={current} max={bar}")
        current -= bar

        # right
        # gc.SetBrush(wx.Brush(wx.Colour(255, 255, 0)))
        x = size - width
        y = width
        bar = size
        # current = max(0, current - bar)
        length = max(0, min(current, bar - width))
        gc.DrawRectangle(x, y, width, length)
        # print(f"Right {x}, {y}, len={length} current={current} max={bar}")
        current -= bar - width

        # bottom
        # gc.SetBrush(wx.Brush(wx.Colour(0, 255, 0)))
        y = size - width
        bar = size
        length = max(0, min(current, bar - width))
        x = size - length - width
        gc.DrawRectangle(x, y, length, width)
        # print(f"Btm   {x}, {y}, len={length} current={current} max={bar}")
        current -= bar - width

        # left
        # gc.SetBrush(wx.Brush(wx.Colour(255, 255, 255)))
        x = 0
        bar = size
        length = max(0, min(current, bar))
        y = size - length - width
        gc.DrawRectangle(x, y, width, length)
        # print(f"Left  {x}, {y}, len={length} current={current} max={bar}")
        current -= bar - width

        # top left
        # gc.SetBrush(wx.Brush(wx.Colour(255, 0, 255)))
        x = width
        y = 0
        bar = round(size / 2)
        length = max(0, min(current, bar - width))
        gc.DrawRectangle(x, y, length, width)
        # print(f"TopL {x}, {y}, len={length} current={current} max={bar}")

        icon = wx.Icon()
        icon.CopyFromBitmap(bmp)

        self.SetIcon(icon, self.title)
        del gc
        del dc
