"""
Memory reclaim helpers for the 512 MB free-tier worker.

The problem these solve, measured live via ``/api/diag/probe``: one cold upload
peaks at the 512 MB cgroup limit, survives (the kernel evicts page cache), but
leaves resident memory ~65 MB above its idle baseline — and that memory never
comes back on its own. ``gc.collect()`` frees the Python objects, yet glibc's
allocator keeps the pages in its arena instead of returning them to the kernel,
so RSS stays high. The *next* upload then starts from that raised floor and
OOM-kills the worker (observed as an empty-body 502 / connection reset).

``malloc_trim(0)`` forces glibc to hand the free top-of-heap back to the OS,
dropping RSS between uploads so each one starts from the same low baseline.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import gc

from app.utils.logger import logger

# Resolved once. None means "no glibc malloc_trim here" — musl (Alpine), macOS
# and Windows have no such symbol, and we must degrade to a plain gc there
# rather than raise. The production image is python:3.11-slim (glibc), where it
# is present.
_libc: ctypes.CDLL | None = None
_resolved = False


def _get_libc() -> ctypes.CDLL | None:
    global _libc, _resolved
    if _resolved:
        return _libc
    _resolved = True
    try:
        name = ctypes.util.find_library("c") or "libc.so.6"
        lib = ctypes.CDLL(name)
        if hasattr(lib, "malloc_trim"):
            lib.malloc_trim.argtypes = [ctypes.c_size_t]
            lib.malloc_trim.restype = ctypes.c_int
            _libc = lib
        else:
            _libc = None
    except Exception as exc:  # noqa: BLE001 - best-effort; never break a request
        logger.debug(f"malloc_trim unavailable ({exc}); using gc only")
        _libc = None
    return _libc


def trim_memory() -> None:
    """
    Collect garbage, then return glibc's free heap to the OS.

    Safe to call from a request's ``finally`` block: it never raises, and on
    platforms without ``malloc_trim`` it is just a ``gc.collect()``.
    """
    gc.collect()
    libc = _get_libc()
    if libc is not None:
        try:
            libc.malloc_trim(0)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"malloc_trim call failed: {exc}")
