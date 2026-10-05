# BijectionLens release-boundary review

Review date: 2026-10-05

## Conclusion

No unresolved critical or important security, resource-boundary, CLI, or archive-content issue was found in the reviewed final runtime snapshot. The important filesystem-error issue discovered during this review was repaired and independently retested. This conclusion is limited to the checks below; it is not a claim of an operating-system memory guarantee or completed remote CI.

## Independent results

- 44 adversarial release-boundary probes passed on Python 3.12.14 against the installed wheel
- The same 44 probes passed against a separately installed source distribution on Python 3.12.14
- The same 44 probes passed against the source package on Python 3.13.5
- All 154 published unit tests passed against the isolated installed wheel on Python 3.12.14
- Runtime source hashes remained unchanged within every final adversarial run
- The independently built wheel contains 19 files, including 13 runtime Python modules and MIT licensing metadata
- The source distribution contains 69 files. Every runtime module in both archives exactly matches the reviewed source
- All 17 historical evidence-file presentation hashes match their provenance manifest

The archive and run receipts identify their exact content hashes. These are local audit artifacts; later rebuilt distributions and a public commit require their own identity checks.

## Findings and resolution

### Important: symlink-loop filesystem errors used the mismatch exit code

On Python 3.12, a cyclic output symlink caused `Path.resolve()` to raise an uncaught `RuntimeError`. The command exited 1 with a traceback and no JSON, incorrectly sharing the documented mathematical-mismatch exit code.

The repair narrowly adapts the Python 3.11/3.12 `ELOOP` wrapper into a filesystem error. Independent input-loop and output-loop probes now return ERROR JSON and exit 4. Embedded-NUL direct `main(argv)` paths return invalid JSON and exit 2. An embedded NUL cannot occur in an operating-system argument vector; that case checks direct-entrypoint robustness.

### Previously reported issues rechecked

- Redirected regular-file stdin is identified by device/inode. Same-path, hard-link and symlink output aliases all return invalid without changing the original file, including with overwrite requested
- Oversized bottleneck pair storage is capped at 62,500 pairs; the schema documentation agrees with the implemented limit
- Bounded decimal parsing and formatting work under Python's lowered 640-digit conversion setting. A subnormal exact threshold with a 647-digit denominator is produced and independently verified without changing the process-global setting
- An integration audit detected stale build-directory bytecode in an in-place wheel rebuild. Fresh staging and member auditing exclude that contamination. Explicit package discovery and disabled implicit package data were also checked with injected bytecode and non-package-text sentinels; neither sentinel entered the wheel

The minor test-only file-handle warning observed during review was also repaired by closing the AST-independence check's source read. It did not affect runtime behavior or certificate results.

## Boundaries exercised

### Hostile inputs and certificate replay

The reviewer read the source, documentation and tests. Additional probes checked raw input, certificate and envelope byte rejection before JSON parsing; oversized JSON numeric tokens before integer conversion; rational digit and bit rejection before `Fraction` construction; oversized matching evidence; all result-field families with callback-raising objects; and malformed worker protocol records.

Canonical hexadecimal coordinates are length-checked before `float.fromhex`. Original sequences, certificate containers and scalar types are checked before traversal or arithmetic. Rational components have fixed character and bit bounds before expensive rational operations. The command input cannot select a Python target, import a callback, load a pickle, fetch a network object, or execute a payload. The private test worker targets are not reachable from JSON input.

### Resource and process semantics

The probes distinguish mathematical mismatch, malformed input, operation exhaustion and unexpected failure. An independently resource-limited replay preserves the candidate's mathematical status while returning exit 3. A limited solver result contains no mathematical certificate.

Real spawned-process tests exercised an unfinished result file, a crash after writing a plausible result, a missing result, and an oversized result. Timeout tests confirmed that no child remained registered. A child explicitly ignoring SIGTERM was killed and joined; its recorded PID no longer existed after supervision returned.

The deadline begins after `Process.start`. Parent parsing, process cleanup, serialization and publication are outside that worker deadline. Library operation counters and bounded input sizes are not a hard RAM quota or an end-to-end command timeout. The documentation makes those limitations explicit.

### Publication, packaging and privacy

Two real simultaneous publishers targeted the same absent output. Exactly one succeeded and the other returned exit 4; the published file was complete, valid, independently verified JSON. Temporary publication files were removed. Existing-file alias protections and failed-write behavior were also checked by the published tests.

Both release archives were checked for absolute/traversing member paths, bytecode, cache directories, `.pth` files, unexpected links/special members, internal planning files, private paths and credential-shaped strings. No such content was found. MIT license text is included. Package metadata has no runtime `Requires-Dist` entries; every runtime absolute import is from Python's standard library. NumPy/SciPy remain optional example or qualification dependencies.

This review does not certify scientific accuracy of supplied numerical values, arbitrary-scale performance, hostile concurrent directory replacement, or an exact public commit's Python 3.11–3.14 CI status.

## Supporting receipts

- `adversarial_review.py`: independent reproducer and probe runner
- `adversarial-final-wheel.json`: final installed-wheel results
- `adversarial-final-sdist.json`: final installed-source-distribution results
- `adversarial-python313-final.json`: Python 3.13 results
- `unit-installed-wheel-final.log`: published unit-suite outcome
- `archive-audit-final.json`: final audit archive members, source equality, metadata and hashes
- `metadata-fixed-audit.json`: injected bytecode/non-package-data exclusion check
- `reviewed-files-sha256.json`: reviewed repository file identities
