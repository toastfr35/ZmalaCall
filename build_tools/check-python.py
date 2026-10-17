"""Check the terminal's Python requirements without shell quoting."""
import ctypes
import struct
import tkinter  # noqa: F401 -- importing verifies that the launcher can load Tk.

if not hasattr(ctypes, 'WinDLL') or struct.calcsize('P') != 8:
    raise RuntimeError('The terminal requires a 64-bit Windows Python with Tkinter.')
