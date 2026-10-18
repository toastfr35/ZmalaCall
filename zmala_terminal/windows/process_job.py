"""Windows Job Object ownership: closing the handle terminates all command descendants."""
import ctypes as C
from ctypes import wintypes as W


class BasicLimits(C.Structure):
    _fields_ = [('process_time', C.c_int64), ('job_time', C.c_int64), ('flags', W.DWORD),
                ('minimum', C.c_size_t), ('maximum', C.c_size_t), ('processes', W.DWORD),
                ('affinity', C.c_size_t), ('priority', W.DWORD), ('scheduling', W.DWORD)]


class ExtendedLimits(C.Structure):
    _fields_ = [('basic', BasicLimits), ('io', C.c_uint64 * 6), ('process_memory', C.c_size_t),
                ('job_memory', C.c_size_t), ('peak_process', C.c_size_t), ('peak_job', C.c_size_t)]


class ProcessJob:
    """Closing this job stops our command and any children it started."""
    def __init__(self):
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        for name, result, args in [
                ('CreateJobObjectW', W.HANDLE, [C.c_void_p, W.LPCWSTR]),
                ('SetInformationJobObject', W.BOOL, [W.HANDLE, C.c_int, C.c_void_p, W.DWORD]),
                ('AssignProcessToJobObject', W.BOOL, [W.HANDLE, W.HANDLE]),
                ('CloseHandle', W.BOOL, [W.HANDLE])]:
            function = getattr(self.kernel, name)
            function.restype, function.argtypes = result, args
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise C.WinError(C.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, C.byref(limits), C.sizeof(limits)):
            self.close()
            raise C.WinError(C.get_last_error())

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise C.WinError(C.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


