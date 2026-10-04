"""Keep all descendants of the owned worker in one kill-on-close Windows job."""

import ctypes

from moru.errors import MoruError


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong),
        ("job_time", ctypes.c_longlong),
        ("flags", ctypes.c_ulong),
        ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t),
        ("active_process_limit", ctypes.c_ulong),
        ("affinity", ctypes.c_size_t),
        ("priority", ctypes.c_ulong),
        ("scheduling", ctypes.c_ulong),
    ]


class IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "read_operations",
            "write_operations",
            "other_operations",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", BasicLimits),
        ("io", IoCounters),
        ("process_memory_limit", ctypes.c_size_t),
        ("job_memory_limit", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


class WindowsJob:
    def __init__(self, kernel=None):
        self._kernel = kernel or ctypes.WinDLL("kernel32", use_last_error=True)
        if kernel is None:
            self._kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
            self._kernel.CreateJobObjectW.restype = ctypes.c_void_p
            self._kernel.SetInformationJobObject.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.c_ulong,
            ]
            self._kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self._kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self._handle = self._kernel.CreateJobObjectW(None, None)
        limits = ExtendedLimits()
        limits.basic.flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self._handle or not self._kernel.SetInformationJobObject(
            self._handle,
            9,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            self.close()
            raise MoruError("IMAGE_WORKER_START_FAILED")

    def assign(self, process_handle):
        if not self._kernel.AssignProcessToJobObject(self._handle, int(process_handle)):
            raise MoruError("IMAGE_WORKER_START_FAILED")

    def close(self):
        if self._handle:
            self._kernel.CloseHandle(self._handle)
            self._handle = None
