# Narrow pixel observations for the verification demo

`decode_rgb_png(raw)` returns `(width, height, rgb_bytes)`. `observe(raw)` returns
red/green/blue component lists with `left`, `top`, `right`, `bottom`, `pixels` and
`shape`. Right/bottom coordinates are exclusive. This module reads actual encoded
pixels and imports no fixture IDs, questions, answer keys or generator labels.

Supported input is deliberately narrow: nonempty bytes up to 2 MiB, PNG signature,
IHDR then contiguous IDAT chunks then empty IEND, no other chunks/trailing bytes.
Every chunk length and CRC is checked. Dimensions must be 1–256 per side; depth 8,
RGB color type 2, standard compression, row filter 0, and no interlacing are required.
Zlib output is capped to expected scanline bytes plus one byte and must end exactly;
truncation, extra output, concatenated streams and compressed trailing data fail.
No unbounded decompression or general image-format fallback is used.

Only the documented exact palette is accepted: red (220,30,30), green (20,150,50),
blue (30,70,220), white (255,255,255), and optional black (0,0,0) axes/background.
Unsupported colors, antialiasing, metadata, alternate filters or PNG profiles raise
ValueError. White and black are ignored by component observation.

Same-color components use four-connectivity (no diagonal or row-edge wrapping),
with a visited bitmap and queue. Output lists follow row-major discovery order.
A component filling its bounding box is square if its sides match, otherwise
rectangle. This takes precedence for one-pixel and other small degenerate shapes.
An exact circle has an odd square bounding box with integer center and radius
(side-1)/2: all component points satisfy the disk equation and the component count
matches the exact integer-filled disk. Even-center disks, ellipses, holes, outlines
and arbitrary shapes are unknown rather than approximately fitted.

These are exact synthetic raster observations, not general visual understanding,
OCR, semantic evidence, arbitrary chart comprehension or a model-quality claim.
The limits bound bytes, raster dimensions and decompression; no process isolation
or proof of real-world image authenticity is provided. The source zlib runtime and
trusted Python process remain part of the execution environment.

Tests independently construct PNG pixels and corrupt streams without importing
fixture answers: square/rectangle/disk geometry, four-connectivity, unknown shapes,
background, palette/profile/filter limits, CRC/order/end checks, bounds, overflow,
truncation and representation-independent observations.
