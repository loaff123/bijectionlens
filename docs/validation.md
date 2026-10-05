# Local release qualification

Checked on 2026-10-05. This records local evidence, not an exact public commit's
remote CI status. Python 3.11–3.14 is the declared support target; local execution
covered Python 3.12.14 and 3.13.5. Python 3.11/3.14 and the exact public commit's
remote workflow remain to be established.

## Verified coverage

- All 154 standard-library unit tests pass on both locally available interpreters
- The [full Python 3.12 qualification](evidence/production/full-python312.json)
  passes 66,067 exhaustive small graphs, 500 rectangular graphs, 2,000 additional
  SciPy graph comparisons, 240 extreme spatial graphs, 10,000 exact predicates,
  600 frozen comparisons, 36 permutation pairs, 16 boundaries, five utility
  baselines, 580 permutation-enumerated bottleneck cases and 12 NumPy examples
- The [Python 3.13 core qualification](evidence/production/core-python313.json)
  passes the dependency-free mathematical profile
- NumPy 2.3.5 and SciPy 1.17.0 are test-only baselines. All 12 exploratory NumPy
  examples match; nine sorting successes and three false negatives are retained
- Source hashes and qualification-runner hashes are recorded in each receipt
- [Independent numerical review](evidence/reviews/numerical/NUMERICAL_REVIEW.md)
  and [independent release-boundary review](evidence/reviews/release/RELEASE_REVIEW.md)
  found no unresolved finding within their stated scopes after regression fixes

The review folders include independent scripts, raw final receipts, source
identities and preserved negative evidence. `PRESENTATION_MANIFEST.json` records
any presentation-only replacement of executor-specific paths. The production
qualification script emits its full per-case JSONL record when rerun; these larger
records are also retained in the build-review packet rather than duplicated here.

## Resource calibration

[Final capacity receipts](evidence/production/capacity.json) report separate fresh
Linux child processes, including imports and independent verification in peak RSS:

| Synthetic case | Result | Solver time | Observed peak RSS |
| --- | --- | ---: | ---: |
| Exact frozen sparse 10,000-point grid | Matched and independently valid | 2.644 s | 27,262,976 bytes |
| Dense 400-by-400 coincident control | Resource-limited at 20,000 edges | See receipt | See receipt |
| Extreme 250-by-250 bottleneck | Resource-limited at 100,000 cumulative edges | See receipt | 79,859,712 bytes |
| Extreme 500-by-500 bottleneck | Resource-limited at 62,500 stored pairs | See receipt | See receipt |

These are representative cases, not general performance or memory guarantees.
The earlier 250,000-pair ceiling permitted a measured 268,959,744-byte extreme
matrix before edge exhaustion. The [preserved pre-reduction calibration](evidence/production/pre-reduction-calibration.json)
motivated lowering the default and hard bottleneck-pair cap to 62,500. A second
cap may still exhaust sooner. No operating-system hard memory quota is claimed.

## Clean distribution checks

Build release artifacts from a fresh source checkout or clean staging tree.
Reusing a populated setuptools build directory can carry stale bytecode into a
wheel. Package discovery is explicitly restricted, and release validation also
checks every archive member, runtime-source byte identity, MIT license metadata,
absence of runtime dependencies, and absence of cache/private-path content.

The independent review exercised separately installed wheel and source
 distributions outside the checkout, including CLI process and atomic-file
boundaries. Distribution-specific build receipts identify exact tested artifacts;
a subsequently rebuilt archive must be checked again. Installation tests copy only
tests, scripts, examples and pyproject.toml beside the installed package and confirm
that imports come from that installation. No source-tree import shortcut is used.

Exact scientific accuracy, arbitrary-scale performance, and authenticity of
certificates are outside the claim. See the [numerical contract](numerical-contract.md),
[JSON schema](schema-v1.md) and [prior art](prior-art.md).
