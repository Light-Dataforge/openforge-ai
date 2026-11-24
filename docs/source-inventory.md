# Observed source inventories

New pilot request/completion records include the same source_inventory object.
Before creating run output, the runner hashes four fixed local files: its runner,
the model adapter, fixture generator and optional-runtime requirements. Each entry
records a repository-relative path, observed byte count and SHA256. The aggregate
inventory hash covers sorted-key compact JSON of the ordered file entries.
No absolute source root, git process, network, dependency import or model load is
needed. Each file is limited to256 KiB and must be regular, not a leaf symlink or
special file. Source directories must remain trusted and frozen.

This is an observed-source inventory, not execution attestation. Files can differ
from modules already loaded or cached bytecode. Dependencies, model weights,
arbitrary injected adapters and other source files are not inventoried. It does
not prove a git revision, authenticity, reproducibility or scientific validity.
execution_verified is always false. Existing frozen-input and host trust limits
apply; ancestor races and concurrent modifications are not isolated.

Missing/oversized/invalid inventory inputs fail before a new run directory exists.
Older saved sources remain readable without this optional metadata; downstream
verification does not treat declared inventories as trusted evidence. No scores,
model execution, training, paid resource or deployment is introduced.
