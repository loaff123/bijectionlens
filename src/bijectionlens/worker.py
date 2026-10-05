"""Portable spawned worker isolation; operation caps are not a hard memory cap."""
from __future__ import annotations

import multiprocessing
from pathlib import Path
import tempfile

from .codec import CodecLimit, RESULT_BYTES, dumps_bounded, read_bounded, to_dict


class WorkerTimeout(RuntimeError):
    """The worker was terminated at its elapsed-time deadline."""


class WorkerError(RuntimeError):
    """The worker crashed or failed the internal result protocol."""


def _supervise(target, args, *, wall_seconds, max_result_bytes=RESULT_BYTES):
    """Run an internal child function, join it, then read its bounded result.

    The target is an internal/test utility, never taken from input. Result files
    avoid blocking indefinitely on a partially written IPC frame. The elapsed
    budget begins after Process.start returns (parent bootstrap is excluded).
    """
    if wall_seconds <= 0:
        raise WorkerTimeout('worker wall-time budget exhausted')
    with tempfile.TemporaryDirectory(prefix='bijectionlens-worker-') as directory:
        output = str(Path(directory) / 'result.json')
        process = multiprocessing.get_context('spawn').Process(target=target, args=(output, *args))
        try:
            process.start()
            process.join(wall_seconds)
            if process.is_alive():
                process.terminate()
                process.join(.25)
                if process.is_alive():
                    process.kill()
                    process.join()
                raise WorkerTimeout('worker wall-time budget exhausted; child terminated')
            if process.exitcode != 0:
                raise WorkerError('worker exited unexpectedly')
            try:
                with open(output, 'rb') as stream:
                    return read_bounded(stream, max_result_bytes)
            except (OSError, CodecLimit) as error:
                raise WorkerError('missing or oversized worker result') from error
        finally:
            if process.pid is not None:
                if process.is_alive():
                    process.kill()
                    process.join()
                process.close()


def _execute_request(output, request):
    """Internal worker entrypoint; input contains validated builtin values only."""
    from .compare import compare
    from .bottleneck import bottleneck
    from .contract import Limits
    from .verify import verify_comparison, verify_bottleneck
    kind = request['kind']
    limits = Limits(**request['limits'])
    common = {'version': 1, 'kind': kind}
    try:
        actual, expected = request['actual'], request['expected']
        if request['command'] == 'verify':
            if kind == 'compare':
                verified = verify_comparison(actual, expected, atol=request['atol'],
                                             result=request['certificate'], limits=limits)
            else:
                verified = verify_bottleneck(actual, expected, result=request['certificate'], limits=limits)
            envelope = {**common, 'status': verified.status, 'verification': to_dict(verified)}
        else:
            candidate = (compare(actual, expected, atol=request['atol'], limits=limits)
                         if kind == 'compare' else bottleneck(actual, expected, limits=limits))
            if candidate.status == 'resource_limited':
                envelope = {**common, 'status': candidate.status, 'result': to_dict(candidate),
                            'verification': None}
            else:
                verified = (verify_comparison(actual, expected, atol=request['atol'], result=candidate, limits=limits)
                            if kind == 'compare' else verify_bottleneck(actual, expected, result=candidate, limits=limits))
                if verified.status == 'invalid':
                    envelope = {**common, 'status': 'error', 'reason': 'solver certificate failed independent verification'}
                else:
                    envelope = {**common, 'status': candidate.status, 'result': to_dict(candidate),
                                'verification': to_dict(verified)}
        try:
            data = dumps_bounded(envelope, limits.max_result_bytes)
        except CodecLimit:
            data = dumps_bounded({**common, 'status': 'resource_limited',
                                  'reason': 'serialized result exceeds configured byte limit'})
    except Exception:
        # Unexpected solver/verifier exceptions must never become input-invalid.
        data = dumps_bounded({**common, 'status': 'error', 'reason': 'unexpected worker failure'})
    Path(output).write_bytes(data)


def run_request(request, *, wall_seconds):
    return _supervise(_execute_request, (request,), wall_seconds=wall_seconds)
