# Offline saved-pilot report

```sh
python -m apps.pilot_report SOURCE_RUN MANIFEST --output NEW_REPORT.html
```

Revalidates saved pilot accounting and hashes, then recomputes supported claims
from actual image bytes using the offline verification bridge. Every source task
remains visible, including unsupported answers, failures and dry runs. No model is
loaded. Source adapter declarations are shown without authenticating runtime.
Synthetic-fixture results are software checks, not model accuracy.

HTML contains escaped text, no scripts or external assets, and a restrictive
content security policy. It exports saved/normalized answers, pixel-derived expected
values, evidence, failure stage/type and reproduction digests. Reference labels and
raw failure messages are excluded. Raw answers, questions and task IDs may contain private
text: review before sharing.

Source inputs and directories must remain trusted and frozen. Source limits apply;
HTML is capped at 4 MiB. A private temporary directory under the existing output
parent holds recomputed results and is removed on ordinary exit. Final publication
uses the existing private fsynced exclusive hard-link publisher; existing files and
symlinks are never overwritten. This is not hostile-filesystem isolation or a source
snapshot. Process death can leave private staging files. Post-publication sync
failure may leave a complete report despite command failure. No network, paid
resources, model runtime or deployment is required.
