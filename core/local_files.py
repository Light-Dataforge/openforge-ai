"""Bounded regular-file reads for trusted stable local directories."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def read_regular(path: str | Path, limit: int) -> bytes:
    """Reject leaf symlinks and special files before reading; never wait on FIFOs.

    Directory ancestors/host are trusted. This is neither a hostile-filesystem
    sandbox nor a snapshot against concurrent file modification.
    """
    if type(limit) is not int or limit < 1:
        raise ValueError("read limit must be a positive integer")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_NONBLOCK"):
        raise OSError("regular input reads require no-follow/nonblocking support")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("input must be a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
    finally:
        os.close(descriptor)
    if len(raw) > limit:
        raise ValueError("input exceeds its byte limit")
    return raw
