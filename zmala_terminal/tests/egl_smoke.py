"""Validate the Windows EGL renderer against this app's own native widget."""
import ctypes as C
from pathlib import Path
import tkinter as tk
ROOT=Path(__file__).resolve().parents[1]
angle=C.CDLL(str(ROOT.parent/'build_tools/runtime/angle-desktop/runtimes/win-x64/native/av_libglesv2.dll'))
angle.EGL_GetProcAddress.argtypes=[C.c_char_p]
angle.EGL_GetProcAddress.restype=C.c_void_p
def fn(name, result, *args):
    return C.CFUNCTYPE(result,*args)(angle.EGL_GetProcAddress(name.encode()))
P,I=C.c_void_p,C.c_int
display=fn('eglGetDisplay',P,P)(None)
error=fn('eglGetError',I)
major,minor=I(),I()
print('initialize',fn('eglInitialize',I,P,C.POINTER(I),C.POINTER(I))(display,C.byref(major),C.byref(minor)),hex(error()))
attributes=(I*13)(0x3024,8,0x3023,8,0x3022,8,0x3033,4,0x3040,4,0x3021,8,0x3038)
config,count=P(),I()
print('choose',fn('eglChooseConfig',I,P,C.POINTER(I),C.POINTER(P),I,C.POINTER(I))(display,attributes,C.byref(config),1,C.byref(count)),count.value,hex(error()))
root=tk.Tk();frame=tk.Frame(root,width=640,height=480);frame.pack();root.update()
hwnd=frame.winfo_id()
u=C.WinDLL('user32');u.IsWindow.argtypes=[P];u.IsWindow.restype=I
print('widget',hwnd,'IsWindow',u.IsWindow(hwnd))
surface=fn('eglCreateWindowSurface',P,P,P,P,C.POINTER(I))(display,config,hwnd,None)
print('surface',surface,hex(error()))
if surface:
    fn('eglDestroySurface',I,P,P)(display,surface)
root.destroy()
fn('eglTerminate',I,P)(display)
assert surface, 'ANGLE could not create a surface for the native widget'
