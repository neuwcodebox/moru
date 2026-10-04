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


def copy_image(window, content: bytes):
    from System import Action, Array, Byte
    from System.Drawing import Bitmap
    from System.IO import MemoryStream
    from System.Windows.Forms import Clipboard, DataFormats, DataObject

    def write():
        stream = MemoryStream(Array[Byte](content))
        bitmap = None
        try:
            bitmap = Bitmap(stream)
            stream.Position = 0
            clipboard = DataObject()
            clipboard.SetData(DataFormats.Bitmap, bitmap)
            clipboard.SetData("PNG", False, stream)
            # Persist both formats before releasing the image and its backing stream.
            Clipboard.SetDataObject(clipboard, True)
        finally:
            if bitmap is not None:
                bitmap.Dispose()
            stream.Dispose()

    window.native.Invoke(Action(write))
