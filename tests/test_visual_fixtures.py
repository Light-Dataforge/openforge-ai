import hashlib
import importlib.util
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path, PurePosixPath

from core.multimodal.fixtures import generate_fixtures


def decode_png(raw):
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("bad signature")
    position = 8
    chunks = []
    bodies = []
    while position < len(raw):
        size = struct.unpack(">I", raw[position : position + 4])[0]
        kind = raw[position + 4 : position + 8]
        body = raw[position + 8 : position + 8 + size]
        checksum = struct.unpack(">I", raw[position + 8 + size : position + 12 + size])[
            0
        ]
        if checksum != zlib.crc32(kind + body):
            raise ValueError("bad CRC")
        chunks.append(kind)
        bodies.append(body)
        position += size + 12
    if chunks != [b"IHDR", b"IDAT", b"IEND"] or position != len(raw):
        raise ValueError("unexpected structure")
    width, height, depth, color, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", bodies[0]
    )
    if (depth, color, compression, filtering, interlace) != (8, 2, 0, 0, 0):
        raise ValueError("unsupported RGB fixture")
    rows = zlib.decompress(bodies[1])
    stride = width * 3
    if len(rows) != height * (stride + 1):
        raise ValueError("bad raster length")
    if any(rows[y * (stride + 1)] != 0 for y in range(height)):
        raise ValueError("unexpected filter")
    pixels = b"".join(
        rows[y * (stride + 1) + 1 : (y + 1) * (stride + 1)] for y in range(height)
    )
    return width, height, pixels


def points(pixels, width, color):
    return {
        (offset // 3 % width, offset // 3 // width)
        for offset in range(0, len(pixels), 3)
        if tuple(pixels[offset : offset + 3]) == color
    }


def components(coordinates):
    remaining = set(coordinates)
    count = 0
    while remaining:
        stack = [remaining.pop()]
        count += 1
        while stack:
            x, y = stack.pop()
            for neighbor in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
    return count


class VisualFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.manifest = generate_fixtures(self.parent / "first")
        self.records = [
            json.loads(line) for line in self.manifest.read_text().splitlines()
        ]

    def test_exact_manifest_contract_limits_paths_and_hashes(self):
        self.assertEqual(len(self.records), 6)
        self.assertEqual(len({row["id"] for row in self.records}), 6)
        for row in self.records:
            self.assertEqual(
                set(row), {"id", "image", "question", "answer", "image_sha256"}
            )
            relative = PurePosixPath(row["image"])
            self.assertFalse(relative.is_absolute())
            self.assertEqual(relative.as_posix(), row["image"])
            self.assertEqual(relative.parts[0], "images")
            self.assertNotIn("..", relative.parts)
            data = (self.manifest.parent / row["image"]).read_bytes()
            self.assertLessEqual(len(data), 2 * 1024 * 1024)
            self.assertEqual(hashlib.sha256(data).hexdigest(), row["image_sha256"])
            width, height, _ = decode_png(data)
            self.assertEqual((width, height), (128, 96))
            self.assertLessEqual(max(width, height), 512)
            self.assertTrue(row["question"].strip())
            self.assertTrue(row["answer"].strip())

    def test_bytes_and_manifest_are_deterministic_across_directories(self):
        other = generate_fixtures(self.parent / "second")
        self.assertEqual(self.manifest.read_bytes(), other.read_bytes())
        for row in self.records:
            self.assertEqual(
                (self.manifest.parent / row["image"]).read_bytes(),
                (other.parent / row["image"]).read_bytes(),
            )

    def test_labels_match_independently_decoded_geometry(self):
        by_id = {row["id"]: row for row in self.records}
        red, green, blue = (220, 30, 30), (20, 150, 50), (30, 70, 220)

        def raster(name):
            row = by_id["synthetic-" + name + "-v1"]
            width, _, pixels = decode_png(
                (self.manifest.parent / row["image"]).read_bytes()
            )
            return row, width, pixels

        row, width, data = raster("color-red-square")
        self.assertEqual(row["answer"], "red")
        self.assertEqual(len(points(data, width, red)), 40 * 40)
        row, width, data = raster("color-blue-circle")
        self.assertEqual(row["answer"], "blue")
        self.assertEqual(components(points(data, width, blue)), 1)
        row, width, data = raster("count-green-squares")
        self.assertEqual(int(row["answer"]), components(points(data, width, green)))
        row, width, data = raster("count-blue-circles")
        self.assertEqual(int(row["answer"]), components(points(data, width, blue)))
        row, width, data = raster("relative-left")
        self.assertEqual(row["answer"], "left")
        self.assertLess(
            max(x for x, _ in points(data, width, red)),
            min(x for x, _ in points(data, width, blue)),
        )
        row, width, data = raster("chart-tallest-bar")
        heights = {
            name: max(y for _, y in points(data, width, color))
            - min(y for _, y in points(data, width, color))
            + 1
            for name, color in [("red", red), ("green", green), ("blue", blue)]
        }
        self.assertEqual(row["answer"], max(heights, key=heights.get))

    def test_existing_directory_and_symlink_never_clobbered(self):
        original = self.manifest.read_bytes()
        with self.assertRaises(FileExistsError):
            generate_fixtures(self.manifest.parent)
        self.assertEqual(self.manifest.read_bytes(), original)
        empty = self.parent / "existing-empty"
        empty.mkdir()
        with self.assertRaises(FileExistsError):
            generate_fixtures(empty)
        link = self.parent / "linked"
        link.symlink_to(self.manifest.parent, target_is_directory=True)
        with self.assertRaises(FileExistsError):
            generate_fixtures(link)
        self.assertEqual(self.manifest.read_bytes(), original)

    def test_missing_parent_is_not_silently_created(self):
        destination = self.parent / "missing" / "fixtures"
        with self.assertRaises(FileNotFoundError):
            generate_fixtures(destination)
        self.assertFalse(destination.parent.exists())

    def test_independent_png_reader_detects_crc_corruption(self):
        raw = bytearray((self.manifest.parent / self.records[0]["image"]).read_bytes())
        raw[20] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC"):
            decode_png(bytes(raw))

    @unittest.skipUnless(
        importlib.util.find_spec("PIL"), "optional Pillow decoder not installed"
    )
    def test_optional_pillow_independently_decodes_all_fixtures(self):
        from PIL import Image

        for row in self.records:
            path = self.manifest.parent / row["image"]
            width, height, pixels = decode_png(path.read_bytes())
            with Image.open(path) as image:
                image.load()
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (width, height))
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.tobytes(), pixels)


if __name__ == "__main__":
    unittest.main()
