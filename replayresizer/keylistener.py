import pynput
import wx

from replayresizer.keyhandler import KeyHandler


class KeyListener(pynput.keyboard.Listener):
    def __init__(self, handler: KeyHandler):
        pynput.keyboard.Listener.__init__(
            self,
            on_press=lambda k: wx.CallAfter(handler.on_key_press, k),
            on_release=lambda k: wx.CallAfter(handler.on_key_release, k)
        )
