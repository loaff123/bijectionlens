# Evidence provenance and reproducibility

## Distinguish three kinds of evidence

1. **Historical feasibility.** Files in [evidence/history](evidence/history/README.md)
   describe a throwaway experiment, including failures and corrected defects.
   Its results are not production test results
2. **Fresh production qualification.** `scripts/qualify.py` imports the package
   currently installed in the executing interpreter. It records production source
   hashes, the qualification script hash, actual versions, all generated cases and
   a success/failure receipt. Generated logs should be kept outside the source tree
3. **Exact-public-commit CI.** The workflow declares Python 3.11–3.14 and a pinned
   Python 3.12 scientific-baseline profile. A configured workflow, a local run, and
   a built archive do not establish a successful remote run for a specific public
   commit. Check the actual workflow run and its commit before making that claim

This repository does not treat historical measurements as product benchmarks or
imply publication/remote verification from local files.

## Independent expected answers

The qualification runner contains separately written expected-answer code:

- Integer cross products formed directly from builtin `as_integer_ratio()` values
  decide geometric edges, including extreme exponents and subnormals
- Exhaustive subset-state dynamic programming computes graph cardinality without
  any augmenting-path or production matching routine
- Exhaustive permutations minimize the maximum independently calculated exact
  squared distance for bottleneck cases
- SciPy supplies an additional clearly labelled matching baseline using the
  independently constructed tolerance graph
- Certificate checks recompute complete Hall neighborhoods from original inputs,
  not merely supplied edges. Production verifiers are also exercised as targets

The production optimizer, graph builder and arithmetic helpers are imported only
as test targets, never to form expected answers. The oracle's own unit tests include
boundary/subnormal arithmetic, a reassignment case, a non-isolated duplicate shortage,
a deliberately omitted Hall neighbor, and minimum-sum versus bottleneck distinction.
The full script refuses optimized Python execution that disables assertions.

## Frozen and additional coverage

The original random seed and case construction are retained for 600 comparisons
(seed 10467011), 36 three-item permutation pairs, 16 named boundaries, five utility
fixtures and 80 bottleneck cases (seed 10467012). This reproduces those inputs;
reusing inspected cases does not turn them into held-out evidence.

Additional fresh checks are all 66,067 square graphs through dimension four,
500 rectangular graphs, 2,000 random graphs against SciPy in the full profile,
240 complete-versus-indexed spatial graphs, 10,000 predicate checks and 500
bottleneck instances of size at most seven. The latter deliberately use a bounded
factorial mix: 25 size-seven, 75 size-six and 400 size-zero-through-five cases.
The receipt gives the actual counts and fixed seeds. The full profile executes all
12 exploratory NumPy cases and preserves every sorting outcome.

The standard-library core profile explicitly omits the SciPy-dependent random
graphs, minimum-sum baseline and NumPy examples. A core receipt is not a full-profile
receipt. The complete unittest suite separately covers malformed and tampered
certificates, operation budgets, timeout termination, serialization and packaging.

## Commands and immutable run directories

From an environment containing the installed package:

```sh
python -m unittest discover -s tests -v
python scripts/qualify.py --profile core --output-dir /tmp/bijectionlens-core-run
```

For the pinned scientific-baseline profile, use Python 3.12:

```sh
python -m pip install numpy==2.3.5 scipy==1.17.0
python scripts/qualify.py --profile full --output-dir /tmp/bijectionlens-full-run
python examples/numpy_roots.py
```

Output directories must be fresh. `results.jsonl` preserves per-case facts and
`summary.json` records counts, versions, source/runner/results hashes, elapsed time,
and success or the observed exception. A failure stops the run rather than skipping
the failing case. Source hashes are checked again after qualification; a changing
implementation cannot acquire a successful receipt from a mixed-source run.

Hashes are accidental-change identifiers, not signatures or an authenticity system.
Interpreter, dependency, operating-system and hardware changes may alter timing and
exploratory root outputs. A fresh run reports those observations rather than promising
historical sorting counts on every platform.


## Capacity profiles and pair-cap calibration

```sh
python scripts/qualify.py --profile capacity --output-dir /tmp/bijectionlens-capacity-run
```

Each profile runs in a fresh subprocess, separate from SciPy/NumPy imports. The
runner records process peak RSS where supported, solver/total elapsed time, source
hashes, counters and verification status. The profiles are:

- `sparse-10000`: exact replay of the original unit-spaced 100×100 grid, translated
  by 0.125+0.125j, with seed-10467011 actual-order shuffle and tolerance 0.25
- `dense-400`: 400 coincident occurrences per side, with a lowered 20,000-edge cap
- `extreme-bottleneck-250`: 62,500 stored exact pair distances combining huge and
  subnormal components, under the current pair cap
- `extreme-bottleneck-500`: deliberate over-pair-budget control, retaining no
  purported optimum when exhausted

The harness terminates a child after 45 seconds and records `harness_timeout`
without inventing a mathematical result. That is a harness observation, separate
from the product CLI's tested 30-second maximum watchdog. Peak RSS includes child
imports and independent verification; it is an observation, not an enforced quota.

An early fresh-production calibration under the former 250,000-pair cap used
268,959,744 peak-RSS bytes for the extreme 500×500 case and then exhausted the
cumulative 100,000-edge cap after 12.36 seconds. This motivated reducing both the
default and hard `max_bottleneck_pairs` to 62,500. The earlier value is not the public
contract. The original calibration receipt is preserved in
[evidence/calibration/before-pair-cap-reduction.json](evidence/calibration/before-pair-cap-reduction.json).
That receipt's sparse profile was an additional spacing-two grid, not the frozen
capacity replay; the current runner explicitly restores the original sparse inputs.

A fresh reduced-cap run stored all 62,500 extreme-value pairs, observed 79,851,520
peak-RSS bytes, and then correctly returned resource exhaustion at the separate
100,000 cumulative-edge cap. Its [receipt](evidence/calibration/after-pair-cap-reduction.json)
also retains the exact frozen sparse replay and the 500×500 over-pair-budget control.
These source-hashed calibration runs are developmental observations, not final
public-commit qualification.

The reduced cap bounds retained pair count more tightly; it still does not establish
a universal memory bound. Each resource-negative case remains inconclusive, including
when a matrix fits but cumulative threshold-graph edges exhaust their separate cap.

## Privacy, licensing and historical corrections

Original package and test code is under the MIT License. Source references identify
prior art; no third-party source payload is redistributed. The historical presentation
copies preserve numerical values, positive and negative baselines, actual runtime
versions and earlier failed tests. Only private paths and research workspace labels
were sanitized. Their original/presentation hashes and transformation statement are
in [the historical provenance manifest](evidence/history/provenance.json). Original
records remained untouched. Internal work plans are not public package content.

No telemetry, credentials, scientific datasets or private user inputs are required
for any qualification case. All cases are reproducibly generated or documented
synthetic fixtures and public NumPy examples.
