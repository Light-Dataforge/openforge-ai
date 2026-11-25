# Regular-file inputs for evaluation and experiments

The exact-answer evaluator and experiment-manifest CLI now open inputs with
nonblocking/no-follow flags and check the opened descriptor is a regular file
before reading. Previously a FIFO with no writer could block indefinitely in
plain open(), even though the reader promised bounded local-file processing.

References/predictions retain their8MiB limits; experiment metadata retains its
1MiB limit. Reads consume at most limit+1 bytes before rejecting oversize inputs.
Leaf symlinks, directories, FIFOs and other special files are rejected. The CLIs
exit2 with no success JSON for these inputs. Existing strict JSON schemas, hashes,
record limits and metrics remain the same. Source bytes are never modified.

No-follow and nonblocking descriptor support is required; unsupported platforms
fail closed. Linux and macOS are the tested targets. Directory ancestors and host
must remain trusted/stable. This is not a hard wall-clock timeout for regular files
on slow filesystems, a hostile-filesystem sandbox or a snapshot against concurrent
modification. No credentials, model inference, network or paid resource is needed.
