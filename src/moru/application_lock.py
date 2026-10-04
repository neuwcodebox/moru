"""Keep restart recovery exclusive to the process owning the data folder."""

import errno
import sys
from contextlib import contextmanager
from pathlib import Path

from moru.errors import MoruError


@contextmanager
def application_lock(data_dir: Path):
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        lock = (data_dir / ".instance.lock").open("a+b")
    except OSError as exc:
        raise MoruError("DATABASE_FAILED") from exc
    with lock:
        if lock.seek(0, 2) == 0:
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            code = (
                "APP_ALREADY_RUNNING"
                if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK)
                else "DATABASE_FAILED"
            )
            raise MoruError(code) from exc
        # Closing the descriptor releases the OS lock, including after an exception/crash.
        yield
