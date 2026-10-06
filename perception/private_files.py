from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path


@lru_cache(maxsize=1)
def _windows_file_api():
    import ctypes as ct
    from ctypes import wintypes as wt

    class SecurityAttributes(ct.Structure):
        _fields_ = [("length", wt.DWORD), ("descriptor", ct.c_void_p), ("inherit", wt.BOOL)]

    class TokenUser(ct.Structure):
        _fields_ = [("sid", ct.c_void_p), ("attributes", wt.DWORD)]

    kernel = ct.WinDLL("kernel32", use_last_error=True)
    security = ct.WinDLL("advapi32", use_last_error=True)
    ptr, out_ptr = ct.c_void_p, ct.POINTER(ct.c_void_p)
    signatures = [
        (kernel.GetCurrentProcess, [], wt.HANDLE),
        (kernel.CloseHandle, [wt.HANDLE], wt.BOOL),
        (kernel.LocalFree, [ptr], ptr),
        (kernel.CreateFileW, [wt.LPCWSTR, wt.DWORD, wt.DWORD, ct.POINTER(SecurityAttributes), wt.DWORD, wt.DWORD, wt.HANDLE], wt.HANDLE),
        (security.OpenProcessToken, [wt.HANDLE, wt.DWORD, ct.POINTER(wt.HANDLE)], wt.BOOL),
        (security.GetTokenInformation, [wt.HANDLE, ct.c_int, ptr, wt.DWORD, ct.POINTER(wt.DWORD)], wt.BOOL),
        (security.ConvertSidToStringSidW, [ptr, ct.POINTER(wt.LPWSTR)], wt.BOOL),
        (security.ConvertStringSecurityDescriptorToSecurityDescriptorW, [wt.LPCWSTR, wt.DWORD, out_ptr, ct.POINTER(wt.DWORD)], wt.BOOL),
        (security.GetSecurityDescriptorDacl, [ptr, ct.POINTER(wt.BOOL), out_ptr, ct.POINTER(wt.BOOL)], wt.BOOL),
        (security.GetSecurityInfo, [wt.HANDLE, ct.c_int, wt.DWORD, out_ptr, out_ptr, out_ptr, out_ptr, out_ptr], wt.DWORD),
        (security.SetSecurityInfo, [wt.HANDLE, ct.c_int, wt.DWORD, ptr, ptr, ptr, ptr], wt.DWORD),
        (security.EqualSid, [ptr, ptr], wt.BOOL),
    ]
    for function, args, result in signatures:
        function.argtypes, function.restype = args, result
    return kernel, security, SecurityAttributes, TokenUser


def private_append_fd(path: Path) -> int:
    if os.name != "nt":
        fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            if os.fstat(fd).st_uid != os.geteuid():
                raise PermissionError("Private files must be owned by the user running Pam.")
            os.fchmod(fd, 0o600)
            return fd
        except BaseException:
            os.close(fd)
            raise
    import ctypes as ct
    import msvcrt
    from ctypes import wintypes as wt

    kernel, security, SecurityAttributes, TokenUser = _windows_file_api()
    token, sid_text = wt.HANDLE(), wt.LPWSTR()
    descriptor, owner_descriptor, owner = ct.c_void_p(), ct.c_void_p(), ct.c_void_p()
    handle = None
    try:
        if not security.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ct.byref(token)):
            raise ct.WinError(ct.get_last_error())
        needed = wt.DWORD()
        security.GetTokenInformation(token, 1, None, 0, ct.byref(needed))
        if not needed.value:
            raise ct.WinError(ct.get_last_error())
        user_buffer = ct.create_string_buffer(needed.value)
        if not security.GetTokenInformation(token, 1, user_buffer, needed.value, ct.byref(needed)):
            raise ct.WinError(ct.get_last_error())
        user_sid = ct.cast(user_buffer, ct.POINTER(TokenUser)).contents.sid
        if not security.ConvertSidToStringSidW(user_sid, ct.byref(sid_text)):
            raise ct.WinError(ct.get_last_error())
        sddl = f"O:{sid_text.value}D:P(A;;FA;;;{sid_text.value})"
        if not security.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ct.byref(descriptor), None):
            raise ct.WinError(ct.get_last_error())
        present, defaulted, dacl = wt.BOOL(), wt.BOOL(), ct.c_void_p()
        if not security.GetSecurityDescriptorDacl(descriptor, ct.byref(present), ct.byref(dacl), ct.byref(defaulted)):
            raise ct.WinError(ct.get_last_error())
        if not present.value or not dacl.value:
            raise PermissionError("Windows did not provide an owner-only access list.")
        attributes = SecurityAttributes(ct.sizeof(SecurityAttributes), descriptor, False)
        access = 0x80000000 | 0x40000000 | 0x00040000
        handle = kernel.CreateFileW(str(path), access, 3, ct.byref(attributes), 4, 0x80, None)
        if handle == ct.c_void_p(-1).value:
            handle = None
            raise ct.WinError(ct.get_last_error())
        error = security.GetSecurityInfo(handle, 1, 1, ct.byref(owner), None, None, None, ct.byref(owner_descriptor))
        if error:
            raise ct.WinError(error)
        if not owner.value or not security.EqualSid(owner, user_sid):
            raise PermissionError("Private files must be owned by the Windows user running Pam.")
        error = security.SetSecurityInfo(handle, 1, 0x80000004, None, None, dacl, None)
        if error:
            raise ct.WinError(error)
        fd = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_APPEND | os.O_BINARY | os.O_NOINHERIT)
        handle = None
        return fd
    finally:
        if handle is not None:
            kernel.CloseHandle(handle)
        if owner_descriptor.value:
            kernel.LocalFree(owner_descriptor)
        if descriptor.value:
            kernel.LocalFree(descriptor)
        if sid_text:
            kernel.LocalFree(ct.cast(sid_text, ct.c_void_p))
        if token.value:
            kernel.CloseHandle(token)
