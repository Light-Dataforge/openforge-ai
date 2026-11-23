"""Original deterministic visual plumbing fixtures, not research evaluation data."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path

WIDTH = 128
HEIGHT = 96
Color = tuple[int, int, int]
WHITE: Color = (255, 255, 255)
RED: Color = (220, 30, 30)
GREEN: Color = (20, 150, 50)
BLUE: Color = (30, 70, 220)
BLACK: Color = (0, 0, 0)


def _rectangle(pixels: bytearray, box: tuple[int, int, int, int], color: Color) -> None:
    left, top, right, bottom = box
    for y in range(top, bottom):
        for x in range(left, right):
            offset = (y * WIDTH + x) * 3
            pixels[offset : offset + 3] = bytes(color)


def _circle(
    pixels: bytearray, center: tuple[int, int], radius: int, color: Color
) -> None:
    cx, cy = center
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius**2:
                offset = (y * WIDTH + x) * 3
                pixels[offset : offset + 3] = bytes(color)


def _png(pixels: bytearray) -> bytes:
    """Encode RGB PNG with deterministic, uncompressed DEFLATE blocks."""
    stride = WIDTH * 3
    scanlines = b"".join(
        b"\x00" + pixels[y * stride : (y + 1) * stride] for y in range(HEIGHT)
    )
    # RFC 1950/1951 stored blocks avoid zlib compressor-version differences.
    stream = bytearray(b"\x78\x01")
    for start in range(0, len(scanlines), 65535):
        block = scanlines[start : start + 65535]
        stream.append(int(start + len(block) == len(scanlines)))
        stream.extend(struct.pack("<HH", len(block), len(block) ^ 0xFFFF))
        stream.extend(block)
    stream.extend(struct.pack(">I", zlib.adler32(scanlines)))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body))
        )

    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", bytes(stream))
        + chunk(b"IEND", b"")
    )


def _fixtures() -> list[tuple[str, bytearray, str, str]]:
    fixtures = []
    pixels = bytearray(bytes(WHITE) * (WIDTH * HEIGHT))
    _rectangle(pixels, (44, 28, 84, 68), RED)
    fixtures.append(
        (
            "color-red-square",
            pixels,
            "What color is the square? Answer with one lowercase color word.",
            "red",
        )
    )
    pixels = bytearray(bytes(WHITE) * (WIDTH * HEIGHT))
    _circle(pixels, (64, 48), 22, BLUE)
    fixtures.append(
        (
            "color-blue-circle",
            pixels,
            "What color is the circle? Answer with one lowercase color word.",
            "blue",
        )
    )
    pixels = bytearray(bytes(WHITE) * (WIDTH * HEIGHT))
    for x in (16, 54, 92):
        _rectangle(pixels, (x, 36, x + 20, 56), GREEN)
    fixtures.append(
        (
            "count-green-squares",
            pixels,
            "How many green squares are shown? Answer with one digit.",
            "3",
        )
    )
    pixels = bytearray(bytes(WHITE) * (WIDTH * HEIGHT))
    for x in (36, 92):
        _circle(pixels, (x, 48), 15, BLUE)
    fixtures.append(
        (
            "count-blue-circles",
            pixels,
            "How many blue circles are shown? Answer with one digit.",
            "2",
        )
    )
    pixels = bytearray(bytes(WHITE) * (WIDTH * HEIGHT))
    _rectangle(pixels, (16, 32, 48, 64), RED)
    _circle(pixels, (94, 48), 16, BLUE)
    fixtures.append(
        (
            "relative-left",
            pixels,
            "Is the red square to the left or right of the blue circle? "
            "Answer left or right.",
            "left",
        )
    )
    pixels = bytearray(bytes(WHITE) * (WIDTH * HEIGHT))
    _rectangle(pixels, (12, 10, 14, 86), BLACK)
    _rectangle(pixels, (12, 84, 120, 86), BLACK)
    _rectangle(pixels, (28, 56, 46, 84), RED)
    _rectangle(pixels, (60, 40, 78, 84), GREEN)
    _rectangle(pixels, (92, 20, 110, 84), BLUE)
    fixtures.append(
        (
            "chart-tallest-bar",
            pixels,
            "Which bar is tallest? Answer with one lowercase color word.",
            "blue",
        )
    )
    return fixtures


def generate_fixtures(output_dir: str | Path) -> Path:
    """Create six deterministic original images and return manifest.jsonl's Path.

    The destination must not exist (even empty); its parent must exist. Exclusive
    creation prevents overwriting prior data. On I/O failure a partial NEW output
    directory may remain, possibly with an incomplete manifest; existing files remain.
    No clock, random seed, network, decoder or model dependency is used.
    """
    directory = Path(output_dir)
    # Construct all known bounded payloads before touching the destination.
    payloads = [
        (name, _png(pixels), question, answer)
        for name, pixels, question, answer in _fixtures()
    ]
    directory.mkdir(exist_ok=False)
    (directory / "images").mkdir()
    records = []
    for name, png, question, answer in payloads:
        relative = f"images/{name}.png"
        with (directory / relative).open("xb") as stream:
            stream.write(png)
        records.append(
            {
                "id": f"synthetic-{name}-v1",
                "image": relative,
                "question": question,
                "answer": answer,
                "image_sha256": hashlib.sha256(png).hexdigest(),
            }
        )
    manifest = directory / "manifest.jsonl"
    raw = "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    with manifest.open("xb") as stream:
        stream.write(raw.encode("utf-8"))
    return manifest
