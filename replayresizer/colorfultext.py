from typing import List, Union

import wx


class ColorfulText:
    def __init__(self, text: str, color):
        self.text = text
        self.color = color


class ColorfulTextBuilder(List[ColorfulText]):
    def __init__(self, text: str = None, default_color: Union[int, str, wx.Colour] = 0xFFF):
        super().__init__()
        self.default_color = default_color
        if text:
            self.append(ColorfulText(text, default_color))

    def add(self, text: str, color=None):
        self.append(ColorfulText(text, self.default_color if color is None else color))
        return self

    def copy(self) -> List[ColorfulText]:
        return list(self)
