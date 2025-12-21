"""
Windows path helpers.

Why this exists:
Some parts of the app normalize drive-letter paths to UNC paths for stable database keys
and consistent comparisons (e.g. mapped drives like Z:\\ -> \\\\server\\share\\).

The previous implementation used `subprocess.run(["net", "use", "Z:"])` which can cause a
brief console window flash when the app is built as a GUI executable.

This module uses Windows APIs via ctypes, avoiding subprocess and preventing any terminal
window from appearing.
"""

from __future__ import annotations

import os


def resolve_mapped_drive_to_unc(path: str) -> str:
    """
    If `path` is a drive-letter path pointing at a mapped network drive (e.g. Z:\\foo),
    return its UNC equivalent (e.g. \\\\server\\share\\foo). Otherwise return `path`.
    """
    if os.name != "nt":
        return path
    if not path or len(path) < 3:
        return path
    if path[1:3] != ":\\":  # only handle drive-letter paths
        return path

    drive = path[:2]  # e.g. "Z:"

    try:
        import ctypes
        from ctypes import wintypes

        # WNetGetConnectionW maps a local device name (e.g. "Z:") to a remote name (e.g. "\\server\share")
        mpr = ctypes.WinDLL("mpr")
        WNetGetConnectionW = mpr.WNetGetConnectionW
        WNetGetConnectionW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        WNetGetConnectionW.restype = wintypes.DWORD

        ERROR_MORE_DATA = 234
        NO_ERROR = 0

        # Start with a reasonable buffer, grow if needed
        buf_len = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(buf_len.value)
        rc = WNetGetConnectionW(drive, buf, ctypes.byref(buf_len))
        if rc == ERROR_MORE_DATA:
            buf = ctypes.create_unicode_buffer(buf_len.value)
            rc = WNetGetConnectionW(drive, buf, ctypes.byref(buf_len))

        if rc != NO_ERROR:
            return path

        unc_root = buf.value
        if not unc_root.startswith("\\\\"):
            return path

        relative_path = path[3:]  # drop "Z:\"
        # Always use Windows separators for our storage/comparison behavior
        joined = os.path.join(unc_root, relative_path).replace("/", "\\")
        return joined
    except Exception:
        # Any failure: keep original path (we don't want playback to fail due to normalization)
        return path


