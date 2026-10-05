"""Independent release-boundary probes. Run with the candidate installed or on PYTHONPATH."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

import bijectionlens as bl
from bijectionlens import codec, cli, worker

RESULTS = []


def probe(name, function):
    start = time.monotonic()
    try:
        details = function()
        RESULTS.append({"id": name, "status": "passed", "details": details,
                        "seconds": round(time.monotonic() - start, 6)})
    except Exception as error:
        RESULTS.append({"id": name, "status": "failed", "error_type": type(error).__name__,
                        "error": str(error), "seconds": round(time.monotonic() - start, 6)})


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


def request(actual=(0,), expected=(0,), atol=0, kind="compare"):
    points = lambda xs: [[complex(x).real.hex(), complex(x).imag.hex()] for x in xs]
    result = {"version": 1, "actual": points(actual), "expected": points(expected)}
    if kind == "compare":
        result["atol_hex"] = float(atol).hex()
    return result


def invoke(payload, *, command="compare", arguments=(), expected_code=0):
    raw = payload if type(payload) is bytes else json.dumps(payload).encode("ascii")
    result = subprocess.run([sys.executable, "-m", "bijectionlens", command, "-", *arguments],
                            input=raw, capture_output=True, timeout=12)
    expect(result.returncode == expected_code, f"exit {result.returncode}, expected {expected_code}; stdout={result.stdout[:300]!r}; stderr={result.stderr[:300]!r}")
    expect(not result.stderr, f"unexpected stderr {result.stderr[:300]!r}")
    body = json.loads(result.stdout)
    return body


def status_probe(payload, expected_code, status, command="compare"):
    result = invoke(payload, command=command, expected_code=expected_code)
    expect(result["status"] == status, str(result))
    return {"exit": expected_code, "status": result["status"],
            "verification": (result.get("verification") or {}).get("status")}


def supervised_ignore_term(output, pid_file):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    Path(pid_file).write_text(str(os.getpid()))
    time.sleep(10)
    Path(output).write_bytes(b"{}")


def supervised_partial(output):
    Path(output).write_bytes(b'{"version":')
    time.sleep(10)


def supervised_crash_after_write(output):
    Path(output).write_bytes(b'{"status":"valid"}')
    os._exit(17)


def supervised_missing(output):
    pass


def supervised_oversized(output):
    Path(output).write_bytes(b"x" * 1025)


def process_probe(target, expected, max_bytes=codec.RESULT_BYTES):
    before = {p.pid for p in multiprocessing.active_children()}
    start = time.monotonic()
    try:
        worker._supervise(target, (), wall_seconds=.5, max_result_bytes=max_bytes)
    except expected:
        pass
    else:
        raise AssertionError("supervisor returned instead of expected failure")
    elapsed = time.monotonic() - start
    expect(elapsed < 2.5, f"supervisor stalled for {elapsed}")
    expect({p.pid for p in multiprocessing.active_children()} == before, "unjoined child remains")
    return {"outcome": expected.__name__, "elapsed": elapsed, "child_joined": True}


def kill_escalation():
    with tempfile.TemporaryDirectory() as directory:
        pid_path = Path(directory) / "pid"
        start = time.monotonic()
        try:
            worker._supervise(supervised_ignore_term, (str(pid_path),), wall_seconds=.7)
        except worker.WorkerTimeout:
            pass
        else:
            raise AssertionError("SIGTERM-ignoring child survived")
        expect(pid_path.exists(), "child never reached signal-handler setup")
        pid = int(pid_path.read_text())
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise AssertionError("terminated child is still present")
        return {"kill_and_join_confirmed": True, "seconds": time.monotonic() - start}


def raw_bound(payload, command):
    with patch.object(codec.json, "loads", side_effect=AssertionError("parser called before raw bound")):
        try:
            codec.parse_request(payload, command)
        except codec.CodecLimit:
            return {"rejected_before_json_loads": True, "bytes": len(payload)}
    raise AssertionError("oversized document accepted")


def numeral_bound():
    with patch.object(codec, "int", side_effect=AssertionError("integer conversion before size bound"), create=True):
        try:
            codec.loads_bounded(b"9" * 100000)
        except codec.CodecError:
            return {"rejected_before_integer_conversion": True}
    raise AssertionError("oversized numeric token accepted")


def rational_bound(field, digits):
    verify = importlib.import_module("bijectionlens.verify")
    result = bl.to_dict(bl.bottleneck([], []))
    result[field] = digits
    with patch.object(verify, "Fraction", side_effect=AssertionError("arithmetic before certificate bound")):
        check = verify.verify_bottleneck([], [], result=result)
    expect(check.status == "resource_limited", check.status)
    return {"status": check.status, "digits": len(digits)}


def stdout_capture():
    class Capture:
        def __init__(self):
            self.buffer = io.BytesIO()
        def flush(self):
            pass
    return Capture()


def path_error(which):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "input.json"
        source.write_text(json.dumps(request()))
        loop = root / "loop"
        loop.symlink_to("loop")
        source_path = str(loop) if which == "input" else str(source)
        output_path = str(loop) if which == "output" else str(root / "output.json")
        run = subprocess.run([sys.executable, "-m", "bijectionlens", "compare", source_path,
                              "--output", output_path], capture_output=True, timeout=12)
        expect(run.returncode == 4, f"filesystem loop returns exit {run.returncode}; stderr={run.stderr[:150]!r}")
        expect(json.loads(run.stdout)["status"] == "error", "filesystem error lacks ERROR JSON")
        expect(not run.stderr, "filesystem error emitted traceback")
        return {"exit": 4, "status": "error"}


def nul_argv(which):
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "input.json"
        source.write_text(json.dumps(request()))
        arguments = ["compare", "a\0b"] if which == "input" else ["compare", str(source), "--output", "a\0b"]
        capture = stdout_capture()
        with patch("sys.stdout", capture):
            code = cli.main(arguments)
        expect(code in (2, 4), f"invalid filesystem argv exit {code}")
        body = json.loads(capture.buffer.getvalue())
        expect(body["status"] in ("invalid", "error"), str(body))
        return {"exit": code, "status": body["status"], "scope": "direct main(argv); OS argv cannot contain NUL"}


def stdin_alias(alias):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "input.json"
        original = json.dumps(request()).encode("ascii")
        source.write_bytes(original)
        output = source if alias == "same" else root / "alias.json"
        if alias == "hardlink":
            os.link(source, output)
        elif alias == "symlink":
            output.symlink_to(source)
        with source.open("rb") as stream:
            run = subprocess.run([sys.executable, "-m", "bijectionlens", "compare", "-", "--output",
                                  str(output), "--overwrite"], stdin=stream, capture_output=True, timeout=12)
        expect(run.returncode == 2, f"stdin alias exit {run.returncode}")
        expect(source.read_bytes() == original, "stdin input overwritten")
        expect(json.loads(run.stdout)["status"] == "invalid", "alias not invalid")
        return {"exit": 2, "input_preserved": True}


def competing_publishers():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "input.json"
        source.write_text(json.dumps(request()))
        output = root / "result.json"
        command = [sys.executable, "-m", "bijectionlens", "compare", str(source), "--output", str(output)]
        children = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        streams = [p.communicate(timeout=12) for p in children]
        expect(sorted(p.returncode for p in children) == [0, 4], "atomic publication did not select one winner")
        body = json.loads(output.read_bytes())
        expect(body["status"] == "matched" and body["verification"]["status"] == "valid", "published invalid result")
        expect(all(not err for _, err in streams), "unexpected publication stderr")
        expect(not list(root.glob(".bijectionlens-*")), "temporary publication file leaked")
        return {"exits": sorted(p.returncode for p in children), "valid_complete_output": True}


def protocol_mutation(field, replacement):
    req = codec.parse_request(json.dumps(request()).encode("ascii"), "compare")
    candidate = bl.compare([0], [0], atol=0)
    envelope = {"version": 1, "kind": "compare", "status": "matched", "result": bl.to_dict(candidate),
                "verification": bl.to_dict(bl.verify_comparison([0], [0], atol=0, result=candidate))}
    if field.startswith("result."):
        envelope["result"][field.split(".", 1)[1]] = replacement
    else:
        envelope[field] = replacement
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "input.json"
        source.write_text(json.dumps(request()))
        capture = stdout_capture()
        with patch.object(cli, "run_request", return_value=json.dumps(envelope).encode("ascii")), patch("sys.stdout", capture):
            code = cli.main(["compare", str(source)])
        expect(code == 4, f"protocol corruption {field} returned {code}")
        expect(json.loads(capture.buffer.getvalue())["status"] == "error", "missing protocol ERROR")
        return {"exit": code, "status": "error"}


def hostile_fields():
    class Hostile:
        def __getattribute__(self, key):
            raise AssertionError("custom attribute callback")
        def __iter__(self):
            raise AssertionError("custom iterator callback")
        def __eq__(self, other):
            raise AssertionError("custom equality callback")
        def __float__(self):
            raise AssertionError("custom numeric callback")
        def __str__(self):
            raise AssertionError("custom text callback")
    base = bl.to_dict(bl.compare([], [], atol=0))
    count = 0
    for field in base:
        altered = dict(base)
        altered[field] = Hostile()
        outcome = bl.verify_comparison([], [], atol=0, result=altered)
        expect(outcome.status == "invalid", f"hostile field {field} not invalid")
        count += 1
    base = bl.to_dict(bl.bottleneck([], []))
    for field in base:
        altered = dict(base)
        altered[field] = Hostile()
        expect(bl.verify_bottleneck([], [], result=altered).status == "invalid", f"hostile bottleneck field {field}")
        count += 1
    return {"hostile_fields_rejected_without_callbacks": count}


def stdlib_scan():
    root = Path(bl.__file__).parent
    imports = set()
    for source in root.glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.Import):
                imports.update(x.name.split(".")[0] for x in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imports.add(node.module.split(".")[0])
    expect(not (imports - sys.stdlib_module_names), str(imports - sys.stdlib_module_names))
    return {"external_imports": sorted(imports), "all_standard_library": True}


def lowered_decimal_limit():
    saved = sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(640)
        candidate = bl.bottleneck([0], [complex(5e-324, 5e-324)])
        expect(candidate.status == "optimal", candidate.status)
        expect(len(candidate.q_denominator) > 640, "fixture does not exceed lowered limit")
        checked = bl.verify_bottleneck([0], [complex(5e-324, 5e-324)], result=candidate)
        expect(checked.status == "valid", checked.status)
        expect(sys.get_int_max_str_digits() == 640, "package mutated process-global limit")
        return {"status": checked.status, "denominator_digits": len(candidate.q_denominator),
                "process_global_limit_unchanged": True}
    finally:
        sys.set_int_max_str_digits(saved)


def hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(bl.__file__).parent.glob("*.py"))}


def main():
    before = hashes()
    probe("matched", lambda: status_probe(request(), 0, "matched"))
    probe("mismatch", lambda: status_probe(request([0], [1]), 1, "mismatch"))
    probe("size-mismatch", lambda: status_probe(request([], [0]), 1, "size_mismatch"))
    probe("invalid-coordinate", lambda: status_probe({**request(), "actual": [["nan", "0x0.0p+0"]]}, 2, "invalid"))
    probe("solver-resource", lambda: status_probe({**request(), "limits": {"max_edges": 0}}, 3, "resource_limited"))
    probe("verifier-resource-retains-candidate", lambda: status_probe({**request(), "limits": {"max_verify_pairs": 0}}, 3, "matched"))
    probe("zero-worker-budget", lambda: status_probe({**request(), "limits": {"max_wall_seconds": 0}}, 3, "resource_limited"))
    probe("tiny-result-budget", lambda: status_probe({**request(), "limits": {"max_result_bytes": 0}}, 3, "resource_limited"))
    probe("optimal", lambda: status_probe(request([0], [1+1j], kind="bottleneck"), 0, "optimal", "bottleneck"))
    probe("optimal-unverified", lambda: status_probe({**request([0], [1+1j], kind="bottleneck"), "limits": {"max_verify_pairs": 0}}, 3, "optimal", "bottleneck"))
    candidate = bl.to_dict(bl.compare([0], [0], atol=0))
    replay = {**request(), "kind": "compare", "certificate": candidate}
    probe("valid-certificate", lambda: status_probe(replay, 0, "valid", "verify"))
    probe("invalid-certificate", lambda: status_probe({**replay, "certificate": {**candidate, "pairs": [[1, 0]]}}, 2, "invalid", "verify"))
    probe("oversized-certificate-pairs", lambda: status_probe({**replay, "certificate": {**candidate, "pairs": [[0, 0]] * 20001}}, 3, "resource_limited", "verify"))
    probe("oversized-input-before-parser", lambda: raw_bound(b" " * (codec.INPUT_BYTES+1), "compare"))
    prefix = b'{"version":1,"kind":"compare","actual":[],"expected":[],"atol_hex":"0x0.0p+0","certificate":'
    probe("oversized-certificate-before-parser", lambda: raw_bound(prefix+b"{"+b" "*codec.RESULT_BYTES+b"}}", "verify"))
    probe("oversized-envelope-before-parser", lambda: raw_bound(b" "*codec.INPUT_BYTES+prefix+b"{}}", "verify"))
    probe("oversized-integer-before-conversion", numeral_bound)
    for field in ("q_numerator", "q_denominator"):
        probe(field+"-digits-bound", lambda field=field: rational_bound(field, "1"*2501))
        probe(field+"-bits-bound", lambda field=field: rational_bound(field, str(1 << 8192)))
    probe("hostile-fields-no-callbacks", hostile_fields)
    probe("timeout-unfinished-result", lambda: process_probe(supervised_partial, worker.WorkerTimeout))
    probe("worker-crash-after-result", lambda: process_probe(supervised_crash_after_write, worker.WorkerError))
    probe("worker-missing-result", lambda: process_probe(supervised_missing, worker.WorkerError))
    probe("worker-oversized-result", lambda: process_probe(supervised_oversized, worker.WorkerError, 1024))
    probe("kill-and-join-escalation", kill_escalation)
    for which in ("input", "output"):
        probe("symlink-loop-"+which, lambda which=which: path_error(which))
        probe("nul-main-argv-"+which, lambda which=which: nul_argv(which))
    for alias in ("same", "hardlink", "symlink"):
        probe("stdin-alias-"+alias, lambda alias=alias: stdin_alias(alias))
    probe("simultaneous-no-clobber-publishers", competing_publishers)
    for field, value in [("version", True), ("kind", "verify"), ("status", "valid"), ("verification", None),
                         ("verification", {"version":1,"status":"invalid","reason":"","counts":[]}),
                         ("result.pairs", [[True, 0]]), ("result.verification_status", "valid")]:
        probe("worker-protocol-"+field+"-"+str(type(value).__name__), lambda field=field,value=value: protocol_mutation(field,value))
    probe("stdlib-import-scan", stdlib_scan)
    probe("lowered-decimal-conversion-limit", lowered_decimal_limit)
    after = hashes()
    report = {"python": sys.version.split()[0], "status": "passed" if all(r["status"] == "passed" for r in RESULTS) and before == after else "failed",
              "source_unchanged": before == after, "source_sha256_before": before, "source_sha256_after": after,
              "passed": sum(r["status"] == "passed" for r in RESULTS), "total": len(RESULTS), "probes": RESULTS}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
