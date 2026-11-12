"""Request shutdown from a previously owned server, after verifying its image and private console."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys


def stop(pid, expected):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                  ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ValueError("Cannot verify the server executable before stopping")
    try:
        name = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(name))
        if not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(length)) or Path(name.value).resolve() != expected.resolve():
            raise ValueError("Refused to stop a different server executable")
        kernel.FreeConsole()
        if not kernel.AttachConsole(pid):
            raise ValueError("Server has no accessible private console")
        members = (wintypes.DWORD * 16)()
        count = kernel.GetConsoleProcessList(members, len(members))
        if count != 2 or set(members[:count]) != {pid, os.getpid()}:
            raise ValueError("Refused to signal a shared Windows console")
        if not kernel.SetConsoleCtrlHandler(None, True) or not kernel.GenerateConsoleCtrlEvent(0, 0):
            raise ValueError("Could not deliver a private Ctrl+C request")
    finally:
        kernel.CloseHandle(handle)


if __name__ == "__main__":
    stop(int(sys.argv[1]), Path(sys.argv[2]))
