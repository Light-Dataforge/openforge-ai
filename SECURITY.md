# Security

The evaluator reads local files and writes JSON only to stdout. It executes no
model code, shell commands, generated code, remote requests or external tools.
Use trusted bounded regular files; named pipes and changing files are not supported
and can block reads. Input is limited to 8 MiB and 10,000 records per file. Avoid
sharing sensitive datasets or raw input. Report hashes may identify known files.

No private vulnerability reporting channel is configured yet. Do not disclose
secrets in public issues. Establish a private contact before public hosting.
Future tool execution requires explicit capabilities and process isolation; this
local evaluator does not provide an execution sandbox.
