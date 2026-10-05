# BijectionLens JSON profile v1

The profile is UTF-8 JSON. It has no executable formats, numeric-object hooks,
network references or external data loading. Unknown and duplicate fields are
rejected at every schema-object level. Verification-envelope field names must be
short literal ASCII strings, without JSON escapes. JSON numbers are integers with magnitude
at most 64 bits; booleans are never accepted as integers. Floating-point JSON
numbers, NaN and Infinity are rejected. Nesting is capped at 16, objects at 64
members, and raw strings at 8,192 characters before JSON container construction.
Each field has the narrower limits below. These are parsing and operation bounds,
not an enforced operating-system memory limit.

## Commands

```
bijectionlens compare examples/compare.json
bijectionlens bottleneck examples/bottleneck.json
bijectionlens verify replay.json
bijectionlens compare input.json --output result.json
bijectionlens compare input.json --output result.json --overwrite --wall-seconds 10
python -m bijectionlens compare - < examples/compare.json
```

A positional input path is required; `-` reads binary standard input. Output is
one deterministic compact JSON document followed by a newline. Without `--output`
it goes to stdout; no progress messages or partial certificates are printed.
Expected errors also produce a JSON document on stdout and leave stderr empty.
If stdout itself fails, the CLI returns 4 and writes a best-effort stderr message;
stdout streams cannot provide atomic publication.
`--help` is conventional text help. Python/interpreter failures outside the CLI
can still produce diagnostic stderr.

Output publication uses a flushed and fsynced temporary file in the destination
directory. Without `--overwrite`, an atomic hard link publishes it only if the
output path is absent. A competing writer cannot be silently overwritten. A
filesystem that does not support hard links produces an output error; there is
no unsafe fallback. `--overwrite` atomically replaces the path. Input/output
aliases, including existing symlinks, hard links and stdin redirected from the
same regular file, are refused even with
`--overwrite`. This protects against accidental aliases; it is not a defense
against an adversary concurrently replacing the input or output directory.
Failures before publication leave no partial result at the output path.

## Request objects

A compare request has exactly these required keys:

- `version`: integer 1
- `actual`, `expected`: arrays of occurrences, at most 20,000 per side
- `atol_hex`: canonical finite nonnegative binary64 `float.hex()` string

The optional `limits` key is an object with any subset of the limits below.
A bottleneck request has the same fields but must omit `atol_hex`.
A verify request adds required `kind` (`"compare"` or `"bottleneck"`) and
`certificate` keys. It includes `atol_hex` only for comparison certificates.

Every occurrence is exactly `[real_hex, imag_hex]`. Both strings are ASCII,
at most 32 characters, and must equal Python's `float.hex()` output for that
finite binary64 coordinate. For example, zero is `"0x0.0p+0"`, one is
`"0x1.0000000000000p+0"`, and negative one is `"-0x1.0000000000000p+0"`.
Canonical negative zero is accepted and compares identically to positive zero.
Decimal strings, shortened hexadecimal spellings and nonfinite values are
invalid. Input order defines occurrence indices; duplicate values remain
separate occurrences.

The predicate uses the exact rational values of the stored coordinates:
`(a.real-b.real)^2 + (a.imag-b.imag)^2 <= atol^2`. There is no relative tolerance
and no separately applied real/imaginary tolerance. This certifies stored values,
not unknown exact roots of a mathematical problem.

## Response envelope and exit codes

Successful solver execution returns:

```
{"version":1,"kind":"compare","status":"matched","result":{...},"verification":{...}}
```

The solver result retains `verification_status: "not_run"`, because it is the
original solver certificate. The sibling `verification` object reports the
subsequent independent replay. A solver-limited result has `verification: null`.
A verify command returns `version`, `kind`, `status` and `verification`, without
`result`. Errors or supervisor/parser limits return `version`, `status` and
`reason`; worker-side errors may also include `kind`.

- 0: matched, valid verification, or independently verified optimal bottleneck
- 1: mismatch or size mismatch, with independently valid evidence
- 2: invalid user input or invalid supplied certificate, including a path
  containing a NUL character
- 3: resource-limited, including an independently unverified solver candidate
- 4: unexpected worker/protocol failure, failed solver-certificate verification,
  or input/output filesystem error, including symbolic-link loops

When verification exhausts its own budget, the solver's mathematical status
remains in `status` and `result.status`, while `verification.status` is
`"resource_limited"` and the process exits 3. This is not an independently
verified answer. Worker timeout yields only a resource-limited outcome, never a
partial success. Invalid independent verification of an internally produced
certificate is an internal error, not an invalid-input result.

## Comparison certificate

`to_dict(ComparisonResult)` contains exactly:

- `version`: 1
- `status`: `matched`, `mismatch`, `size_mismatch` or `resource_limited`
- `actual_size`, `expected_size`: nonnegative occurrence counts
- `pairs`: arrays `[actual_index, expected_index]`, at most 20,000 pairs
- `hall`: null or Hall object below
- `counts`: sorted arrays `[phase, used_count]`
- `reason`: null or bounded explanatory string
- `resource`: null or resource object below
- `verification_status`: `not_run`

A Hall object contains exactly `left_indices`, `neighbor_indices` and
`deficiency`. Index arrays each contain at most 20,000 integers. For a mismatch,
`neighbor_indices` is the entire legal neighborhood of `left_indices`, and
`deficiency = len(left_indices) - len(neighbor_indices)` equals the input size
minus matching cardinality. The verifier checks every opposite-side occurrence
for every listed left occurrence, not just the supplied pairing or listed
neighbors. Feasible pairing plus that deficiency proves maximum cardinality.

Resource objects have exactly `phase`, `used`, `requested`, `limit`. Counts and
indices are builtin nonnegative integers with at most 64 bits, then checked
against semantic bounds. Resource-limited certificates contain no matching or
Hall claim and cannot be replayed as valid mathematical results.

## Bottleneck certificate

`to_dict(BottleneckResult)` contains `version`, `status`, `actual_size`,
`expected_size`, `pairs`, `counts`, `reason`, `resource`, `verification_status`,
and these additional fields:

- `q_numerator`, `q_denominator`: canonical decimal strings for reduced rational
  squared optimum q, or null when no optimum is claimed. At most 2,500 ASCII
  decimal digits each; numerator nonnegative, denominator positive; at most
  8,192 bits before rational construction. No leading zeroes except `"0"`
- `strict_hall`: Hall object for the strict graph `distance_squared < q`, or null
  at q=0 and when no optimum is claimed
- `approximate_atol`: a labelled approximate decimal display string for sqrt(q),
  or null. It never decides acceptance
- `least_finite_binary64_atol`: canonical hex string for the least nonnegative
  finite binary64 t satisfying `t*t >= q`, or null if none exists

Status is `optimal`, `size_mismatch` or `resource_limited`. The pairing proves
feasibility at q; the strict Hall certificate proves impossibility below q.
For q=0, nonnegativity supplies the lower bound. The least binary64 value is
checked against its immediate predecessor when q>0; at q=0 it is positive zero.
An approximate decimal display is never an exact threshold.

## Verification object

Exactly `version` (1), `status` (`valid`, `invalid`, `resource_limited`), `reason`
(string), and `counts` (sorted phase/count arrays). A `valid` status is an
independent certificate replay, not a claim about experimental accuracy.

A replay file is the original request with `kind` and `certificate` added:

```python
import json
import bijectionlens as bl

request = json.load(open("examples/compare.json"))
result = bl.compare([0, 0.9], [0, -0.9], atol=1)
request.update(kind="compare", certificate=bl.to_dict(result))
with open("replay.json", "w") as stream:
    json.dump(request, stream)
```

The verifier accepts omitted optional certificate fields using model defaults;
unknown fields are always invalid. Solver output includes all fields above.

## Hard maxima and lower per-call limits

All limits are builtin nonnegative integers and may lower, never raise, maxima:

| JSON limit name | Maximum |
| --- | ---: |
| max_items | 20,000 per side |
| max_input_bytes | 8,388,608 |
| max_edges | 100,000 |
| max_tree_visits | 2,000,000 |
| max_tree_build | 4,000,000 |
| max_matching_scans | 20,000,000 |
| max_verify_pairs | 2,000,000 |
| max_bottleneck_pairs | 62,500 |
| max_result_bytes | 33,554,432 |
| max_wall_seconds | 30 |
| max_filtration_steps | 250,000 |
| max_filtration_checks | 8,000,000 |

Ordinary input reads stop after at most 8 MiB + 1 bytes. Verification input has
an independent 32 MiB certificate maximum and 8 MiB original-input/envelope
maximum, plus a combined 40 MiB pre-parse maximum. Oversized data is not parsed
as an unrestricted JSON document. Lower request-byte limits are enforced after
reading the hard-bounded request and before normalization. Results have a 32 MiB
hard byte maximum; lowering this bound may replace a result with a small
resource-limit diagnostic. That fixed diagnostic may itself exceed an unusually
small requested output cap; it never includes a certificate.

`--wall-seconds` is an integer 0..30. The smaller of it and `max_wall_seconds`
is the worker budget. Zero immediately returns resource-limited. The parent
starts a spawned worker and joins it with this deadline. At expiry it terminates
and joins the child, escalating to kill and join if necessary. The budget starts
after parent process bootstrap (`Process.start`) and excludes parent bounded
input parsing, serialization, process cleanup and output publication. It is not
an end-to-end shell-command deadline. The parent never waits for an unfinished
IPC frame. Library APIs use operation counters and have no wall-time guarantee.
There is no hard RSS/memory guarantee on Linux or any other platform.
