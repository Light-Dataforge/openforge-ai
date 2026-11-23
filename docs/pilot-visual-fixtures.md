# Original visual smoke fixtures

`core.multimodal.fixtures.generate_fixtures(output_dir: str | Path) -> Path`
creates six tiny original visual inputs and returns the new `manifest.jsonl` path.
The destination directory must not already exist (including empty/symlink paths)
and its parent must exist. Each file uses exclusive creation. No existing files
are overwritten or removed. An I/O failure may leave a newly created partial
folder, possibly with an incomplete manifest; inspect it rather than treating it
as complete.

```python
from core.multimodal.fixtures import generate_fixtures

manifest = generate_fixtures("new-visual-smoke-fixtures")
```

Records have exactly `id`, `image`, `question`, `answer`, `image_sha256`. Image paths
are canonical relative POSIX paths under `images/`; digests bind exact encoded
bytes. Output order, IDs, questions, labels and bytes are deterministic. No random
seed, clock, model, dependency installation or network is involved. The encoder
uses fixed RGB PNG structure and stored DEFLATE blocks rather than a version-varying
compression strategy. Every image is 128×96 and under 2 MiB; there are six examples,
below the pilot's 20-item limit.

Examples check red-square/blue-circle color, three green squares, two blue circles,
left/right placement and a tallest-color bar chart. Labels refer to the original
raster geometry. Reference answers are exact strings intended to exercise input,
model-adapter and export plumbing. Questions do not embed answer hints in text
provided to a model; IDs/file names should be excluded from model prompts.

All raster and question/answer sources are original synthetic MIT-licensed project
fixtures. They are not an external dataset, research benchmark, held-out evaluation,
model result, measured reasoning ability or verification improvement. Known simple
cases can expose pipeline failures, but success does not establish generalization.
No model weights or third-party images are downloaded. Strict $0 budget.

The standard suite independently parses PNG chunks/CRC and decompresses raster
bytes using the standard library, checks limits, stable digests, paths, labels and
no-clobber behavior. Optional independent Pillow decoding runs only when Pillow is
installed; absence is an explicit skip and adds no dependency to ordinary CPU CI.
The parent pilot runner remains responsible for strict manifest validation, path
containment, digest checks and permission/resource bounds before model execution.
