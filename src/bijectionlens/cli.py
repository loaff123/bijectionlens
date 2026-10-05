"""Bounded command-line entrypoint and atomic, no-clobber output publication."""
from __future__ import annotations

import argparse
import errno
import os
from pathlib import Path
import sys
import stat
import tempfile

from .codec import (CodecError, CodecLimit, INPUT_BYTES, RESULT_BYTES, VERIFY_BYTES,
                    COMPARE_FIELDS, BOTTLENECK_FIELDS,
                    dumps_bounded, loads_bounded, parse_request, read_bounded)
from .worker import WorkerError, WorkerTimeout, run_request


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CodecError(message)


def _wall(value):
    if not value.isascii() or not value.isdecimal() or len(value) > 2:
        raise argparse.ArgumentTypeError('wall-seconds must be an integer from 0 to 30')
    answer = int(value)
    if answer > 30:
        raise argparse.ArgumentTypeError('wall-seconds cannot exceed 30')
    return answer


def _stream_identity(stream):
    try:
        info = os.fstat(stream.fileno())
    except (OSError, AttributeError, ValueError):
        return None
    return (info.st_dev, info.st_ino) if stat.S_ISREG(info.st_mode) else None


def _aliases(input_path, output_path, input_identity=None):
    if input_identity is not None:
        try:
            output_info = os.stat(output_path)
            if (output_info.st_dev, output_info.st_ino) == input_identity:
                return True
        except FileNotFoundError:
            pass
    if input_path is None:
        return False
    try:
        same_resolved_path = Path(input_path).resolve() == Path(output_path).resolve()
    except RuntimeError as error:
        # Python 3.11/3.12 pathlib translates ELOOP to RuntimeError; later
        # versions preserve OSError. Adapt only this documented ELOOP case.
        cause = error.__context__
        if not isinstance(cause, OSError) or cause.errno != errno.ELOOP:
            raise
        raise OSError(errno.ELOOP, 'cannot resolve a path containing a symbolic-link loop') from error
    if same_resolved_path:
        return True
    try:
        return os.path.samefile(input_path, output_path)
    except FileNotFoundError:
        return False


def _atomic_write(path, data, *, overwrite, input_path, input_identity=None):
    """Publish an fsynced same-directory temporary file, never check-then-replace."""
    path = Path(path)
    if _aliases(input_path, path, input_identity):
        raise CodecError('input and output must not refer to the same file')
    descriptor, temporary = tempfile.mkstemp(prefix='.bijectionlens-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if _aliases(input_path, path, input_identity):
            raise CodecError('input and output must not refer to the same file')
        if overwrite:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _exit_code(envelope):
    status = envelope.get('status')
    verification = envelope.get('verification')
    if type(verification) is dict and verification.get('status') == 'resource_limited':
        return 3
    return {'matched': 0, 'valid': 0, 'optimal': 0, 'mismatch': 1, 'size_mismatch': 1,
            'invalid': 2, 'resource_limited': 3, 'error': 4}.get(status, 4)


def _validate_worker_envelope(envelope, request):
    from .models import (ComparisonResult, BottleneckResult, VerificationResult,
                         HallEvidence, ResourceEvidence)
    from .contract import ResourceLimit
    try:
        if type(envelope) is not dict or type(envelope.get('version')) is not int or envelope['version'] != 1:
            raise ValueError('wrong envelope version')
        if envelope.get('kind') != request['kind']:
            raise ValueError('wrong envelope kind')
        status = envelope.get('status')
        base = {'version', 'kind', 'status'}
        if status in ('error', 'resource_limited') and set(envelope) == base | {'reason'}:
            if type(envelope['reason']) is not str or len(envelope['reason']) > 4096:
                raise ValueError('malformed diagnostic')
            return
        if request['command'] == 'verify':
            if set(envelope) != base | {'verification'}:
                raise ValueError('malformed verification envelope')
            result = None
        else:
            if set(envelope) != base | {'result', 'verification'}:
                raise ValueError('malformed solver envelope')
            raw = envelope['result']
            fields = COMPARE_FIELDS if request['kind'] == 'compare' else BOTTLENECK_FIELDS
            if type(raw) is not dict or set(raw) != set(fields) or raw['status'] != status:
                raise ValueError('malformed solver certificate')
            kwargs = dict(raw)
            hall_key = 'hall' if request['kind'] == 'compare' else 'strict_hall'
            if kwargs[hall_key] is not None:
                if type(kwargs[hall_key]) is not dict:
                    raise ValueError('malformed Hall evidence')
                kwargs[hall_key] = HallEvidence(**kwargs[hall_key])
            if kwargs['resource'] is not None:
                if type(kwargs['resource']) is not dict:
                    raise ValueError('malformed resource evidence')
                kwargs['resource'] = ResourceEvidence(**kwargs['resource'])
            model = ComparisonResult if request['kind'] == 'compare' else BottleneckResult
            result = model(**kwargs)
            if status == 'resource_limited':
                if envelope['verification'] is not None:
                    raise ValueError('limited candidate cannot claim verification')
                return
        raw_check = envelope['verification']
        if type(raw_check) is not dict or set(raw_check) != {'version', 'status', 'reason', 'counts'}:
            raise ValueError('malformed verification record')
        checked = VerificationResult(**raw_check)
        if request['command'] == 'verify':
            if checked.status != status:
                raise ValueError('inconsistent verification status')
        elif checked.status == 'invalid':
            raise ValueError('invalid solver certificate')
    except (TypeError, ValueError, KeyError, ResourceLimit) as error:
        raise WorkerError('invalid worker result protocol') from error


def _send_stdout(data):
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
        return True
    except OSError:
        # Do not retry a broken stream or allow interpreter shutdown to turn the
        # explicit error status into an unrelated buffered-flush exit status.
        try:
            descriptor = os.open(os.devnull, os.O_WRONLY)
            try:
                os.dup2(descriptor, sys.stdout.fileno())
            finally:
                os.close(descriptor)
        except (OSError, AttributeError, ValueError):
            pass
        try:
            sys.stderr.write('bijectionlens: output stream failed\n')
            sys.stderr.flush()
        except OSError:
            pass
        return False


def main(argv=None):
    parser = _Parser(prog='bijectionlens', description='Exact bounded unordered binary64 comparison')
    parser.add_argument('command', choices=('compare', 'bottleneck', 'verify'))
    parser.add_argument('input', help='v1 JSON file, or - for standard input')
    parser.add_argument('--output', help='atomically write JSON to this path instead of stdout')
    parser.add_argument('--overwrite', action='store_true', help='allow replacing an existing output file')
    parser.add_argument('--wall-seconds', type=_wall, default=30, help='worker wall budget, integer 0..30')
    output = None
    try:
        options = parser.parse_args(argv)
        if '\x00' in options.input or (options.output is not None and '\x00' in options.output):
            raise CodecError('input and output paths cannot contain NUL characters')
        input_path = None if options.input == '-' else options.input
        output = options.output
        if output and _aliases(input_path, output):
            raise CodecError('input and output must not refer to the same file')
        maximum = VERIFY_BYTES if options.command == 'verify' else INPUT_BYTES
        if input_path is None:
            input_identity = _stream_identity(sys.stdin.buffer)
            if output and _aliases(None, output, input_identity):
                raise CodecError('input and output must not refer to the same file')
            raw = read_bounded(sys.stdin.buffer, maximum)
        else:
            with open(input_path, 'rb') as stream:
                input_identity = _stream_identity(stream)
                raw = read_bounded(stream, maximum)
        request = parse_request(raw, options.command)
        wall = min(options.wall_seconds, request['limits'].get('max_wall_seconds', 30))
        encoded = run_request(request, wall_seconds=wall)
        try:
            envelope = loads_bounded(encoded, RESULT_BYTES)
            _validate_worker_envelope(envelope, request)
        except (CodecError, CodecLimit) as error:
            raise WorkerError('malformed worker result protocol') from error
        code = _exit_code(envelope)
        if output:
            _atomic_write(output, encoded, overwrite=options.overwrite, input_path=input_path, input_identity=input_identity)
        else:
            if not _send_stdout(encoded):
                return 4
        return code
    except CodecLimit as error:
        envelope = {'version': 1, 'status': 'resource_limited', 'reason': str(error)}
        code = 3
    except CodecError as error:
        envelope = {'version': 1, 'status': 'invalid', 'reason': str(error)}
        code = 2
    except WorkerTimeout as error:
        envelope = {'version': 1, 'status': 'resource_limited', 'reason': str(error)}
        code = 3
    except (WorkerError, OSError) as error:
        envelope = {'version': 1, 'status': 'error', 'reason': str(error)}
        code = 4
    return code if _send_stdout(dumps_bounded(envelope)) else 4
