"""Twelve exploratory comparisons; all sorting controls are retained.

Requires optional NumPy. Run after installing BijectionLens. This example does
not test a root solver's true numerical accuracy or claim a new solver defect.
"""
import json
import platform

import numpy as np
from bijectionlens import compare, verify_comparison


def cases():
    for n in (2, 3, 4, 5, 6, 8, 12, 16):
        coefficients = np.zeros(n + 1)
        coefficients[0] = coefficients[-1] = 1
        yield (f"initial-control-x{n}-plus-one", np.roots(coefficients).tolist(),
               np.polynomial.polynomial.polyroots(coefficients).tolist())
    for i, roots in enumerate(((-1j, 0, 1j), (-1j, 1j), (-1j, 0, 1j, 2),
                               (-2j, -1j, 0, 1j, 2j))):
        coefficients = np.polynomial.polynomial.polyfromroots(roots)
        yield (f"known-root-{i}", np.polynomial.polynomial.polyroots(coefficients).tolist(),
               list(roots))


def run():
    rows = []
    for name, actual, expected in cases():
        result = compare(actual, expected, atol=1e-12)
        check = verify_comparison(actual, expected, atol=1e-12, result=result)
        rows.append({"id": name, "status": result.status, "verification": check.status,
                     "pairs": result.pairs,
                     "sorted_allclose": bool(np.allclose(np.sort_complex(actual),
                                                          np.sort_complex(expected),
                                                          atol=1e-12, rtol=0))})
    report = {"classification": "exploratory; not held out; all cases retained",
              "python": platform.python_version(), "numpy": np.__version__,
              "cases": rows, "sorting_passes": sum(row["sorted_allclose"] for row in rows),
              "sorting_false_negatives": sum(row["status"] == "matched" and not row["sorted_allclose"]
                                              for row in rows)}
    print(json.dumps(report, indent=2, sort_keys=True))
    return all(row["status"] == "matched" and row["verification"] == "valid" for row in rows)


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
