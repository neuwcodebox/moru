"""Windows clipboard writes on the desktop's STA UI thread."""


def copy_text(window, text: str):
    from System import Action
    from System.Windows.Forms import Clipboard

    def write():
        if text:
            Clipboard.SetText(text)
        else:
            Clipboard.Clear()

    window.native.Invoke(Action(write))
