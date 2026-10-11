"""Small Win32 bridge: hotkey, protected credentials and Unicode input."""
import base64
import ctypes as c
from ctypes import wintypes as w
import os
import time

user32 = c.WinDLL("user32", use_last_error=True)
crypt32 = c.WinDLL("crypt32", use_last_error=True)
kernel32 = c.WinDLL("kernel32", use_last_error=True)
user32.GetForegroundWindow.restype = w.HWND
user32.IsWindow.argtypes = [w.HWND]
user32.SetForegroundWindow.argtypes = [w.HWND]
user32.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
user32.RegisterHotKey.argtypes = [w.HWND, c.c_int, w.UINT, w.UINT]
user32.UnregisterHotKey.argtypes = [w.HWND, c.c_int]
user32.PeekMessageW.argtypes = [c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT]
user32.GetAsyncKeyState.argtypes = [c.c_int]
user32.GetAsyncKeyState.restype = c.c_short
kernel32.LocalFree.argtypes = [c.c_void_p]
kernel32.LocalFree.restype = c.c_void_p


def foreground():
    return user32.GetForegroundWindow()


def is_our_window(hwnd):
    pid = w.DWORD()
    user32.GetWindowThreadProcessId(hwnd, c.byref(pid))
    return pid.value == os.getpid()


class Hotkey:
    """Native global shortcut on the GUI thread; no keyboard hook required."""
    def __init__(self, modifiers=3, key=0x20):
        self.registered = bool(user32.RegisterHotKey(None, 0x4242, 0x4000 | modifiers, key))

    def poll(self):
        message = w.MSG()
        return bool(user32.PeekMessageW(c.byref(message), w.HWND(-1), 0x0312, 0x0312, 1))

    def close(self):
        if self.registered:
            user32.UnregisterHotKey(None, 0x4242)
            self.registered = False


class Blob(c.Structure):
    _fields_ = [("size", w.DWORD), ("data", c.POINTER(c.c_ubyte))]


crypt32.CryptProtectData.argtypes = [c.POINTER(Blob), w.LPCWSTR, c.POINTER(Blob),
    c.c_void_p, c.c_void_p, w.DWORD, c.POINTER(Blob)]
crypt32.CryptUnprotectData.argtypes = [c.POINTER(Blob), c.c_void_p, c.POINTER(Blob),
    c.c_void_p, c.c_void_p, w.DWORD, c.POINTER(Blob)]


def _protect(data, decrypt=False):
    buffer = (c.c_ubyte * len(data)).from_buffer_copy(data)
    source = Blob(len(data), buffer)
    result = Blob()
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    if not function(c.byref(source), None, None, None, None, 1, c.byref(result)):
        raise c.WinError(c.get_last_error())
    try:
        return c.string_at(result.data, result.size)
    finally:
        kernel32.LocalFree(result.data)


def protect_key(key):
    return base64.b64encode(_protect(key.encode("utf-8"))).decode("ascii") if key else ""


def unprotect_key(value):
    return _protect(base64.b64decode(value, validate=True), True).decode("utf-8") if value else ""


class KeyboardInput(c.Structure):
    _fields_ = [("vk", w.WORD), ("scan", w.WORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("extra", c.c_size_t)]


class MouseInput(c.Structure):
    _fields_ = [("x", w.LONG), ("y", w.LONG), ("data", w.DWORD),
                ("flags", w.DWORD), ("time", w.DWORD), ("extra", c.c_size_t)]


class InputUnion(c.Union):
    _fields_ = [("keyboard", KeyboardInput), ("mouse", MouseInput)]


class Input(c.Structure):
    _anonymous_ = ("payload",)
    _fields_ = [("type", w.DWORD), ("payload", InputUnion)]


user32.SendInput.argtypes = [w.UINT, c.POINTER(Input), c.c_int]
user32.SendInput.restype = w.UINT


def insert_text(text, target):
    """Don't steal focus from a different app or touch the clipboard."""
    if not target or not user32.IsWindow(target):
        return False
    current = foreground()
    if current != target:
        if not is_our_window(current) or not user32.SetForegroundWindow(target):
            return False
        time.sleep(0.15)
    # A hotkey may still be held when a very short recording ends.
    deadline = time.monotonic() + 0.8
    while any(user32.GetAsyncKeyState(key) & 0x8000 for key in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)
    encoded = text.encode("utf-16-le")
    units = [int.from_bytes(encoded[i:i+2], "little") for i in range(0, len(encoded), 2)]
    for offset in range(0, len(units), 32):
        if foreground() != target:
            return False
        batch = []
        for unit in units[offset:offset+32]:
            batch.extend((Input(1, InputUnion(keyboard=KeyboardInput(0, unit, 4, 0, 0))),
                          Input(1, InputUnion(keyboard=KeyboardInput(0, unit, 6, 0, 0)))))
        inputs = (Input * len(batch))(*batch)
        if user32.SendInput(len(batch), inputs, c.sizeof(Input)) != len(batch):
            return False
    return True
