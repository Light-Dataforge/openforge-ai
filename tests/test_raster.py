"""Original pixel geometry and corrupt PNG cases; no fixture labels are imported."""

import struct
import unittest
import zlib
from unittest.mock import patch

from core.verification.raster import decode_rgb_png, observe

RED, GREEN, BLUE, WHITE, BLACK = (
    (220, 30, 30),
    (20, 150, 50),
    (30, 70, 220),
    (255, 255, 255),
    (0, 0, 0),
)


def chunk(kind, body):
    return (
        struct.pack(">I", len(body))
        + kind
        + body
        + struct.pack(">I", zlib.crc32(kind + body))
    )


def png(
    width,
    height,
    pixels,
    *,
    filter_byte=0,
    profile=(8, 2, 0, 0, 0),
    stream=None,
    idat_parts=1,
):
    header = struct.pack(">IIBBBBB", width, height, *profile)
    scanlines = b"".join(
        bytes([filter_byte]) + pixels[y * width * 3 : (y + 1) * width * 3]
        for y in range(height)
    )
    compressed = zlib.compress(scanlines) if stream is None else stream
    parts = [
        compressed[
            i * len(compressed) // idat_parts : (i + 1) * len(compressed) // idat_parts
        ]
        for i in range(idat_parts)
    ]
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + b"".join(chunk(b"IDAT", part) for part in parts)
        + chunk(b"IEND", b"")
    )


def raster(width, height, colored):
    pixels = bytearray(bytes(WHITE) * (width * height))
    for (x, y), color in colored.items():
        position = 3 * (y * width + x)
        pixels[position : position + 3] = bytes(color)
    return png(width, height, bytes(pixels))


class RasterTests(unittest.TestCase):
    def test_decode_actual_rgb_and_split_idat(self):
        data = bytes(RED + WHITE + BLUE + BLACK)
        raw = png(2, 2, data, idat_parts=3)
        self.assertEqual(decode_rgb_png(raw), (2, 2, data))

    def test_filled_square_rectangle_and_exclusive_bounds(self):
        colored = {(x, y): RED for x in range(1, 4) for y in range(2, 5)}
        colored.update({(x, y): GREEN for x in range(6, 10) for y in range(1, 3)})
        report = observe(raster(12, 8, colored))
        self.assertEqual(
            report["red"],
            [
                {
                    "left": 1,
                    "top": 2,
                    "right": 4,
                    "bottom": 5,
                    "pixels": 9,
                    "shape": "square",
                }
            ],
        )
        self.assertEqual(
            report["green"],
            [
                {
                    "left": 6,
                    "top": 1,
                    "right": 10,
                    "bottom": 3,
                    "pixels": 8,
                    "shape": "rectangle",
                }
            ],
        )
        self.assertEqual(report["blue"], [])

    def test_exact_disk_and_disconnected_four_connectivity(self):
        colored = {
            (x, y): BLUE
            for y in range(1, 8)
            for x in range(2, 9)
            if (x - 5) ** 2 + (y - 4) ** 2 <= 9
        }
        colored[(0, 0)] = RED
        colored[(1, 1)] = RED
        report = observe(raster(10, 9, colored))
        self.assertEqual(
            report["blue"],
            [
                {
                    "left": 2,
                    "top": 1,
                    "right": 9,
                    "bottom": 8,
                    "pixels": 29,
                    "shape": "circle",
                }
            ],
        )
        self.assertEqual(len(report["red"]), 2)
        self.assertEqual(
            [(row["left"], row["top"]) for row in report["red"]], [(0, 0), (1, 1)]
        )

    def test_hole_and_irregular_geometry_are_unknown(self):
        colored = {(x, y): RED for x in range(3) for y in range(3) if (x, y) != (1, 1)}
        report = observe(raster(3, 3, colored))
        self.assertEqual(report["red"][0]["shape"], "unknown")
        self.assertEqual(report["red"][0]["pixels"], 8)
        colored = {(0, 0): GREEN, (0, 1): GREEN, (1, 1): GREEN}
        self.assertEqual(observe(raster(3, 3, colored))["green"][0]["shape"], "unknown")

    def test_white_and_black_are_ignored_and_row_edges_do_not_wrap(self):
        colored = {(2, 0): RED, (0, 1): RED, (1, 1): BLACK}
        report = observe(raster(3, 2, colored))
        self.assertEqual(len(report["red"]), 2)
        self.assertEqual(
            observe(raster(1, 1, {(0, 0): BLACK})), {"red": [], "green": [], "blue": []}
        )

    def test_unknown_palette_rejected(self):
        raw = png(1, 1, bytes((219, 30, 30)))
        for function in [decode_rgb_png, observe]:
            with self.assertRaisesRegex(ValueError, "palette"):
                function(raw)

    def test_signature_bounds_crc_and_truncation(self):
        raw = raster(1, 1, {})
        for bad in [
            b"",
            b"not png",
            raw[:-1],
            raw + b"extra",
            raw[:20] + bytes([raw[20] ^ 1]) + raw[21:],
            raw[:8] + b"\xff\xff\xff\xff" + raw[12:],
        ]:
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                decode_rgb_png(bad)
        with (
            patch("core.verification.raster.MAX_BYTES", len(raw) - 1),
            self.assertRaises(ValueError),
        ):
            decode_rgb_png(raw)
        for width, height in [(0, 1), (257, 1), (1, 257)]:
            with self.assertRaisesRegex(ValueError, "dimensions"):
                decode_rgb_png(png(width, height, b""))
        data = bytes(WHITE) * (256 * 256)
        self.assertEqual(decode_rgb_png(png(256, 256, data))[:2], (256, 256))

    def test_profile_and_filter_rejected(self):
        for profile in [
            (16, 2, 0, 0, 0),
            (8, 6, 0, 0, 0),
            (8, 2, 0, 0, 1),
            (8, 2, 1, 0, 0),
        ]:
            with self.assertRaisesRegex(ValueError, "profile"):
                decode_rgb_png(png(1, 1, bytes(WHITE), profile=profile))
        with self.assertRaisesRegex(ValueError, "filter 0"):
            decode_rgb_png(png(1, 1, bytes(WHITE), filter_byte=1))

    def test_chunk_types_order_duplicates_and_nonempty_end_rejected(self):
        header = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        data = chunk(b"IDAT", zlib.compress(b"\x00" + bytes(WHITE)))
        end = chunk(b"IEND", b"")
        for chunks in [
            data + header + end,
            header + header + data + end,
            header + end,
            header + data,
            header + data + chunk(b"tEXt", b"unsupported") + end,
            header + data + chunk(b"IEND", b"x"),
            chunk(b"IHDR", b"short") + data + end,
        ]:
            with self.assertRaises(ValueError):
                decode_rgb_png(b"\x89PNG\r\n\x1a\n" + chunks)

    def test_zlib_overflow_trailing_stream_and_incomplete_output_rejected(self):
        valid_stream = zlib.compress(b"\x00" + bytes(WHITE))
        for stream in [
            valid_stream[:-1],
            valid_stream + b"extra",
            valid_stream + valid_stream,
            zlib.compress(b"\x00"),
            zlib.compress(b"x" * 1000000),
            b"invalid",
        ]:
            with self.subTest(length=len(stream)), self.assertRaises(ValueError):
                decode_rgb_png(png(1, 1, bytes(WHITE), stream=stream))

    def test_same_pixels_same_observation_despite_compressed_representation(self):
        pixels = bytes(RED + WHITE + BLUE + WHITE)
        first = png(2, 2, pixels)
        scanlines = b"\x00" + pixels[:6] + b"\x00" + pixels[6:]
        second = png(
            2, 2, pixels, stream=zlib.compress(scanlines, level=0), idat_parts=2
        )
        self.assertNotEqual(first, second)
        self.assertEqual(observe(first), observe(second))


if __name__ == "__main__":
    unittest.main()
