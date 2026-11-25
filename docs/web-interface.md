# OpenForge visual workspace

The buildless browser interface lives in web/. Preview from this checkout:

```sh
python3 -m http.server 8765 --directory web
```

The visual lab inspects the six original scene images at native canvas resolution,
using actual RGB connected components and conservative shape/claim rules ported
from the Python verifier. Expected answers are computed from pixels, not fixture
answer labels. Correct/wrong/unsupported candidates yield verified/contradicted/
abstained. Evidence bounds, counts and image fingerprints are inspectable, and the
last result can be downloaded. Candidate text remains local unless downloaded/shared.

Overview explains implemented capabilities. Experiments shows the existing actual
six-case scripted replay with every failure/abstention retained. Evidence library
opens generated HTML reports and original synthetic evaluation JSON. These are
static retained artifacts, not freshly executed model runs or live CI statuses.
No model, server API, authentication, uploads, paid endpoint or database is implied.
The public static deployment uses GitHub Pages, as explicitly requested. Relative
assets and hash routes support its repository subpath. No existing backend source
or unmerged research branch is replaced; a dedicated gh-pages branch serves assets.

Verification remains narrow synthetic-geometry software conformance, not general
image reasoning or model accuracy. Source hashes do not authenticate execution.
The page does not download model weights. No billing/runtime installation occurs.

Tests: node --test web/*.test.mjs checks manual RGBA geometry and Python/browser
parity on all six original fixtures and twelve candidate decisions. Real browser
QA covers verified/contradicted/abstained states, navigation and responsive layout.
