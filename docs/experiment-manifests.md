# Version-1 experiment manifests

The evaluator now supports a bounded provenance declaration alongside frozen
reference and prediction files. From the repository root:

```sh
python -m core.experiments examples/synthetic-manifest.json examples/references.jsonl examples/predictions.jsonl
```

The manifest must be a strict UTF-8 JSON object, at most 1 MiB, with exactly these
fields. Duplicate keys, unknown fields, invalid Unicode and nonfinite constants
fail validation. Each textual value is nonblank and at most 16,384 characters.

| Field | Contract |
| --- | --- |
| schema_version | Integer 1; booleans are rejected |
| run_kind | synthetic or model |
| model | For model runs: id, full immutable revision, license declaration; synthetic runs require null |
| dataset | id, full immutable revision, license declaration |
| inputs | reference_sha256 and prediction_sha256; lowercase 64-digit SHA-256 values |
| prompt | For model runs: text and matching UTF-8 sha256; synthetic runs require null |
| preprocessing | id and full immutable revision |
| generation | For model runs: seed, temperature, max_new_tokens; synthetic runs require null |
| environment | Full Python 3.x.y version, platform, hardware, exact-version dependencies map |
| code_revision | Full lowercase 40- or 64-digit commit identifier |

Revisions must be full lowercase 40- or 64-digit hexadecimal identifiers, not
moving labels such as main/latest. Generation requires a seed in [0, 2^32), finite
temperature in [0,2] and max_new_tokens in [1,32768]. Dependency maps have at most
256 entries; versions are exact tokens rather than constraints or moving aliases.
An empty map is valid for a standard-library-only evaluation. Exact versions do
not capture every native library, driver or model runtime; extend the contract
through a reviewed schema version when those become relevant.

The command uses the existing evaluator to validate and hash the bytes actually
read, then compares both input hashes against the declaration. Changed files fail
instead of silently producing scores for different artifacts. Explicit command
arguments supply file paths; the manifest cannot instruct a download or select a
tool. Valid output includes the manifest hash, run kind, exact-answer metrics and
model_execution_verified=false. It omits prompt text and detailed environment
metadata. Invalid input or missing files exits 2 with no partial stdout.

The supplied example binds the three existing synthetic accounting fixtures and
the evaluator code revision. It records this fixture evaluation's environment,
not a VLM experiment. Synthetic manifests must not include invented model/prompt/
generation metadata. Unit-test-only model declarations exercise schema validation
without running models.

## Trust and limits

The validator checks syntax and local artifact binding. It does not fetch model
revisions, verify licenses, prove the declared environment was used, authenticate
an experiment, guarantee deterministic GPU execution or establish model-quality
results. Model license approval and baseline inference remain separate work.
A syntactically valid model declaration still reports model_execution_verified=false.

Use trusted, immutable regular files. Named pipes or concurrently replaced files
are outside the contract; hashes identify bytes read, not a multi-file atomic
snapshot. Manifests themselves can contain private prompts and machine details;
review them before publication. Reports omit that content but their hashes may
identify known artifacts. The copied metadata returned by validate_metadata is
not a signature or attestation.
