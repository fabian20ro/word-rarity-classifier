from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path


@contextmanager
def acquire_output_lock(output_csv_path: Path):
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output_csv_path.with_name(f"{output_csv_path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    handle = lock_path.open("a+b")
    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                f"Another step2 process is already writing to {output_csv_path}."
            ) from exc
        yield
    finally:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        handle.close()
