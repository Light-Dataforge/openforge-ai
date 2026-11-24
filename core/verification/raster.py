"""Narrow dependency-free PNG raster observations, independent of fixture labels."""

from __future__ import annotations

import struct
import zlib
from collections import deque
from math import isqrt
from typing import Any

MAX_BYTES = 2 * 1024 * 1024
MAX_SIDE = 256
SIGNATURE = b"\x89PNG\r\n\x1a\n"
# The observer's explicit profile, not imported task labels or fixture metadata.
PALETTE = {
    bytes((255, 255, 255)): 0,
    bytes((0, 0, 0)): 0,
    bytes((220, 30, 30)): 1,
    bytes((20, 150, 50)): 2,
    bytes((30, 70, 220)): 3,
}
NAMES = {1: "red", 2: "green", 3: "blue"}


def _labels(pixels: bytes) -> bytearray:
    result = bytearray()
    for offset in range(0, len(pixels), 3):
        color = PALETTE.get(pixels[offset : offset + 3])
        if color is None:
            raise ValueError("unsupported RGB palette value")
        result.append(color)
    return result


def decode_rgb_png(raw: bytes) -> tuple[int, int, bytes]:
    """Decode only the documented bounded fixture PNG profile; no general PNG API."""
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError("PNG input must be nonempty bytes of at most 2 MiB")
    if not raw.startswith(SIGNATURE):
        raise ValueError("invalid PNG signature")
    position = len(SIGNATURE)
    width = height = 0
    compressed = []
    state = "header"
    ended = False
    while position < len(raw):
        if len(raw) - position < 12:
            raise ValueError("truncated PNG chunk")
        length = struct.unpack_from(">I", raw, position)[0]
        if length > len(raw) - position - 12:
            raise ValueError("chunk length exceeds input")
        kind = raw[position + 4 : position + 8]
        body = raw[position + 8 : position + 8 + length]
        checksum = struct.unpack_from(">I", raw, position + 8 + length)[0]
        if zlib.crc32(kind + body) != checksum:
            raise ValueError("PNG chunk CRC mismatch")
        position += length + 12
        if kind == b"IHDR" and state == "header":
            if length != 13:
                raise ValueError("invalid IHDR length")
            width, height, depth, color, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", body)
            )
            if not 1 <= width <= MAX_SIDE or not 1 <= height <= MAX_SIDE:
                raise ValueError("PNG dimensions exceed 1..256 per side")
            if (depth, color, compression, filtering, interlace) != (8, 2, 0, 0, 0):
                raise ValueError("unsupported PNG profile")
            state = "data"
        elif kind == b"IDAT" and state in {"data", "more_data"}:
            compressed.append(body)
            state = "more_data"
        elif kind == b"IEND" and state == "more_data" and length == 0:
            ended = True
            break
        else:
            raise ValueError("unsupported PNG chunk or chunk order")
    if not ended or position != len(raw):
        raise ValueError("missing PNG end or trailing data")
    expected = height * (width * 3 + 1)
    decoder = zlib.decompressobj()
    try:
        scanlines = decoder.decompress(b"".join(compressed), expected + 1)
    except zlib.error as exc:
        raise ValueError("invalid zlib image stream") from exc
    if (
        len(scanlines) != expected
        or not decoder.eof
        or decoder.unused_data
        or decoder.unconsumed_tail
    ):
        raise ValueError("invalid, truncated or oversized zlib stream")
    stride = width * 3 + 1
    if any(scanlines[y * stride] != 0 for y in range(height)):
        raise ValueError("only PNG row filter 0 is supported")
    pixels = b"".join(
        scanlines[y * stride + 1 : (y + 1) * stride] for y in range(height)
    )
    _labels(pixels)
    return width, height, pixels


def _shape(
    points: list[tuple[int, int]], left: int, top: int, right: int, bottom: int
) -> str:
    width, height = right - left, bottom - top
    if len(points) == width * height:
        return "square" if width == height else "rectangle"
    if width == height and width % 2 == 1:
        radius = (width - 1) // 2
        cx, cy = left + radius, top + radius
        expected = sum(
            2 * isqrt(radius * radius - y * y) + 1 for y in range(-radius, radius + 1)
        )
        if len(points) == expected and all(
            (x - cx) ** 2 + (y - cy) ** 2 <= radius**2 for x, y in points
        ):
            return "circle"
    return "unknown"


def observe(raw: bytes) -> dict[str, list[dict[str, Any]]]:
    """Observe connected exact-palette regions from pixels alone, without an answer key.

    Boxes use exclusive right/bottom bounds. Components are four-connected and
    listed in row-major discovery order. White and black pixels are background.
    """
    width, height, pixels = decode_rgb_png(raw)
    labels = _labels(pixels)
    visited = bytearray(width * height)
    observations: dict[str, list[dict[str, Any]]] = {
        name: [] for name in NAMES.values()
    }
    for start, color in enumerate(labels):
        if not color or visited[start]:
            continue
        visited[start] = 1
        queue = deque([start])
        points = []
        left, top, right, bottom = width, height, 0, 0
        while queue:
            position = queue.popleft()
            x, y = position % width, position // width
            points.append((x, y))
            left, top, right, bottom = (
                min(left, x),
                min(top, y),
                max(right, x + 1),
                max(bottom, y + 1),
            )
            neighbors = []
            if x > 0:
                neighbors.append(position - 1)
            if x + 1 < width:
                neighbors.append(position + 1)
            if y > 0:
                neighbors.append(position - width)
            if y + 1 < height:
                neighbors.append(position + width)
            for neighbor in neighbors:
                if not visited[neighbor] and labels[neighbor] == color:
                    visited[neighbor] = 1
                    queue.append(neighbor)
        observations[NAMES[color]].append(
            {
                "left": left,
                "top": top,
                "right": right,
                "bottom": bottom,
                "pixels": len(points),
                "shape": _shape(points, left, top, right, bottom),
            }
        )
    return observations
