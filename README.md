# BijectionLens

Exact, bounded comparison of unordered finite real or complex numerical results.
Every occurrence matters, including duplicates. BijectionLens finds a global
one-to-one pairing under an explicit absolute modulus tolerance, or explains a
shortage with a certificate that can be checked against the original inputs.

The runtime uses only Python's standard library. Python 3.11–3.14 is the declared
support target. The CI matrix is configured; its presence is not evidence that a
particular commit has passed remote CI. See [evidence provenance](docs/evidence-provenance.md)
for the distinction between historical feasibility experiments and fresh production qualification.
The [local validation report](docs/validation.md) lists the checked profiles and remaining CI gates.

## Install from this checkout

```sh
python -m pip install .
```

No NumPy or SciPy dependency is needed to use the library or CLI. An optional
NumPy example and the full qualification profile use test-only dependencies.

## Compare and independently check

```python
from bijectionlens import compare, verify_comparison

actual = [0.75, 0.0]
expected = [0.0, 1.5]
result = compare(actual, expected, atol=0.8)
assert result.status == "matched"
assert set(result.pairs) == {(0, 1), (1, 0)}

check = verify_comparison(actual, expected, atol=0.8, result=result)
assert check.status == "valid"
```

A first-fit strategy can choose `0.75 → 0.0` and get stuck. Global matching can
reassign that occurrence. Even exact common values must remain available for
reassignment when tolerance neighborhoods overlap.

For a negative result:

```python
result = compare([0, 0, 3], [0, 3, 3], atol=0.1)
assert result.status == "mismatch"
assert result.hall.left_indices == (0, 1)
assert result.hall.neighbor_indices == (0,)
assert result.hall.deficiency == 1
```

The first two actual occurrences have only one compatible expected occurrence.
The Hall witness contains their complete neighbor set. It need not be the
smallest or uniquely explanatory deficient subset. A feasible partial matching
plus this deficiency proves the reported matching size is maximum.

## The precise contract

- Inputs are builtin lists or tuples of finite builtin `float` or `complex`
  values; builtin integers are accepted only when exactly representable as binary64
- Booleans, arbitrary numeric objects, unsized iterators, NaN and infinity are rejected
- `atol` is a finite, nonnegative binary64 absolute tolerance. There is no relative tolerance
- A pair is legal exactly when the sum of squared real/imaginary differences is
  at most `atol²`, using exact arithmetic on the supplied stored values
- Duplicates retain separate occurrence indices; signed zeros are equivalent
- Results have explicit statuses and no implicit truth value. Check `.status`
- Exhausting a budget returns `resource_limited`, an inconclusive outcome with no
  numerical pass/fail or claimed optimum
- Independent verification has its own budget and can also be inconclusive

This compares stored numerical results. It does not establish the accuracy of
roots, eigenvalues, or the underlying scientific computation. See the complete
[numerical contract and limits](docs/numerical-contract.md).

Successful matching and independent verification certify only scalar-value correspondence. They do not establish the identity or continuity of a physical state or root branch through a parameter sweep, even when the bottleneck radius is zero.

## Exact bottleneck diagnostic

```python
from fractions import Fraction
from bijectionlens import bottleneck, verify_bottleneck

result = bottleneck([0], [1 + 1j])
assert result.status == "optimal"
q = Fraction(int(result.q_numerator), int(result.q_denominator))
assert q == 2
assert verify_bottleneck([0], [1 + 1j], result=result).status == "valid"
```

`q` is the exact smallest **squared** absolute tolerance permitting a bijection.
The radius is `sqrt(q)`, which may be irrational. `approximate_atol` is only a
readable approximation. `least_finite_binary64_atol` is a separately proved
canonical hex value, or `None` if no finite binary64 tolerance suffices. For zero,
it is positive zero. A full matching at `q` and a complete-neighbor Hall shortage
for distances strictly below `q` establish optimality. The zero case instead uses
nonnegativity for its lower bound. This diagnostic does not recommend a scientifically
appropriate tolerance.

## Portable JSON CLI

CLI inputs use canonical finite `float.hex()` strings, including coordinates as
`[real_hex, imag_hex]`, so the stored values can be replayed without decimal ambiguity.

```sh
printf '%s\n' '{"version":1,"actual":[["0x1.8000000000000p+1","0x1.0000000000000p+2"]],"expected":[["0x0.0p+0","0x0.0p+0"]],"atol_hex":"0x1.4000000000000p+2"}' > request.json
bijectionlens compare request.json --output result.json
```

Commands are `compare`, `bottleneck`, and `verify`. Use `-` as the input path for
stdin. An existing output file is preserved unless `--overwrite` is explicit.
The CLI supervises a separate worker under an integer wall-time budget of at
most 30 seconds. Exit codes are 0 for a matched/valid result or independently
verified bottleneck, 1 for mismatch/size mismatch, 2 for invalid input/certificate,
3 for resource exhaustion, and 4 for an unexpected worker, protocol or I/O failure. See the [v1 schema](docs/schema-v1.md) for requests,
result envelopes and verification-status details.

## NumPy roots example

```sh
python examples/numpy_roots.py
```

Convert arrays with `.tolist()` before passing them to the API. The example
replays all 12 exploratory root-comparison cases, including every sorting success.
The earlier NumPy 2.3.5 experiment matched all 12, while sorting matched nine and
false-failed three. Those cases were inspected exploratory examples, not held-out
evidence or a NumPy solver bug report. Fresh execution prints the actual NumPy
version and every result rather than assuming those historical counts.

## Reproduce qualification

```sh
python -m unittest discover -s tests -v
python scripts/qualify.py --profile core --output-dir /tmp/bijectionlens-core-evidence
```

The core profile independently checks all 66,067 square bipartite graphs through
4×4, 500 rectangular graphs, 240 extreme-exponent spatial graphs, 10,000 exact
integer-cross-product predicates, the 600 frozen comparisons, 36 permutation
pairs, 16 boundary cases, five utility controls and 580 all-permutation bottleneck
cases. The 500 additional bottleneck cases include 25 size-seven and 75 size-six
instances; the remaining sizes are zero through five.

The full test-only profile adds 2,000 random SciPy graph checks, SciPy comparison
baselines, minimum-sum assignment controls and all 12 NumPy root examples:

```sh
python -m pip install numpy==2.3.5 scipy==1.17.0
python scripts/qualify.py --profile full --output-dir /tmp/bijectionlens-full-evidence
```

Use a fresh output directory for each run. The script imports the installed
package, emits every case and records source hashes, actual dependency versions
and a success/failure receipt. Expected results come from independent integer
arithmetic, exhaustive subset-state DP, exhaustive permutations, and the explicitly
identified SciPy baseline. It never uses the production optimizer as its oracle.

Qualification is not a universal performance guarantee. The package has explicit
operation caps; dense graphs can exhaust them. Portable operation limits and a
CLI wall watchdog do not imply a hard operating-system memory limit. The bottleneck
pair cap is 62,500 (at most 250×250 for equal-sized inputs); it was reduced after
extreme-value memory calibration. See the provenance guide for the preserved
measurement and its limited scope.

## Existing solutions and evidence

SciPy already supplies correct maximum bipartite matching after construction of
the desired edge graph. GoogleTest already supplies unordered predicate matching
and partial-pair diagnostics. This package claims no new matching algorithm.
See [prior art](docs/prior-art.md), [historical evidence](docs/evidence/history/README.md),
and [provenance](docs/evidence-provenance.md) for the narrow motivation and limitations.

Licensed under the [MIT License](LICENSE).
