# Audit a saved observed-source inventory

```sh
python -m apps.source_audit SAVED_RUN_DIRECTORY
```

Strictly checks optional source-inventory metadata and compares its four declared
file hashes/byte counts with current observed source bytes. Exit0 means matching
observations; exit1 means differences or unavailable metadata in an older source;
exit2 means invalid metadata or I/O. Complete JSON includes only fixed relative
file names and aggregate hashes, never source contents, answers or absolute roots.
No file is modified. The saved run is bounded regular no-follow JSON with duplicate
keys rejected. Inventories require exact fields, types, order, finite byte limits
and internally consistent SHA256. Current files follow the capture bounds.

A matching receipt is not authenticated provenance. Anyone can edit declarations
and recompute hashes. This command does not validate results/manifests/weights or
establish what code ran, whether a model executed, or whether code is safe. Current
files can differ from modules already loaded. execution_verified remains false.
Sources/ancestors must be trusted and frozen; no hostile-filesystem isolation or
atomic source snapshot is claimed. No optional model imports, downloads or paid
resource is required. For actual result checks use pilot_verification instead.
