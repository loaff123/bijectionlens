"""Resource boundary and real supervisor termination tests."""
import io
import json
import os
from pathlib import Path
import time

import tempfile
import unittest
from unittest.mock import patch


def _delayed_child(output, marker):
    time.sleep(2)
    Path(marker).write_text('child survived')
    Path(output).write_bytes(b'{}')


def _crashed_child(output):
    os._exit(9)


def _valid_child(output):
    Path(output).write_bytes(b'{"status":"valid"}')


class ResourceLimitTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)

    def test_supervisor_terminates_delayed_worker_and_joins(self):
        from bijectionlens.worker import WorkerTimeout, _supervise
        marker = self.path / 'late-marker'
        started = time.monotonic()
        with self.assertRaises(WorkerTimeout):
            _supervise(_delayed_child, (str(marker),), wall_seconds=.1)
        self.assertLess(time.monotonic() - started, 1.5)
        time.sleep(2.1)
        self.assertFalse(marker.exists())

    def test_worker_crash_is_an_error_and_success_returns_bytes(self):
        from bijectionlens.worker import WorkerError, _supervise
        with self.assertRaises(WorkerError):
            _supervise(_crashed_child, (), wall_seconds=5)
        self.assertEqual(_supervise(_valid_child, (), wall_seconds=5), b'{"status":"valid"}')

    def test_bounded_reader_reads_only_limit_plus_one(self):
        from bijectionlens.codec import CodecLimit, read_bounded
        stream = io.BytesIO(b'x' * 100)
        with self.assertRaises(CodecLimit):
            read_bounded(stream, 8)
        self.assertEqual(stream.tell(), 9)

    def test_json_nesting_is_rejected_without_recursion_error(self):
        from bijectionlens.codec import CodecError, loads_bounded
        with self.assertRaises(CodecError):
            loads_bounded(b'[' * 1000 + b']' * 1000)

    def test_atomic_no_clobber_handles_competing_writer(self):
        from bijectionlens.cli import _atomic_write
        output = self.path / 'result.json'
        link = os.link
        def competitor(source, destination):
            output.write_bytes(b'competitor')
            return link(source, destination)
        with patch('os.link', competitor), self.assertRaises(FileExistsError):
            _atomic_write(output, b'candidate', overwrite=False, input_path=None)
        self.assertEqual(output.read_bytes(), b'competitor')
        self.assertEqual(sorted(p.name for p in self.path.iterdir()), ['result.json'])

    def test_interrupted_write_does_not_publish_partial_result(self):
        from bijectionlens.cli import _atomic_write
        output = self.path / 'result.json'
        with patch('os.fsync', side_effect=OSError('interrupted fsync')), self.assertRaises(OSError):
            _atomic_write(output, b'candidate', overwrite=False, input_path=None)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.path.iterdir()), [])

    def test_verify_certificate_raw_bytes_are_bounded_before_json_parse(self):
        from bijectionlens.codec import CodecLimit, parse_request
        raw = b'{"version":1,"kind":"compare","actual":[],"expected":[],"atol_hex":"0x0.0p+0","certificate":{' + b' ' * (32 * 1024 * 1024) + b'}}'
        with self.assertRaises(CodecLimit):
            parse_request(raw, 'verify')

    def test_verify_original_input_raw_bytes_have_separate_bound(self):
        from bijectionlens.codec import CodecLimit, parse_request
        raw = b'{"version":1,"kind":"compare","actual":[' + b' ' * (8 * 1024 * 1024) + b'],"expected":[],"atol_hex":"0x0.0p+0","certificate":{"status":"matched","actual_size":0,"expected_size":0}}'
        with self.assertRaises(CodecLimit):
            parse_request(raw, 'verify')

    def test_serializer_rejects_arbitrary_hooks(self):
        from bijectionlens import to_dict
        class Dangerous:
            def __getattribute__(self, name):
                raise AssertionError('serialization hook invoked')
        with self.assertRaises(TypeError):
            to_dict(Dangerous())

    def test_codec_duplicate_nested_keys_and_noncanonical_hex(self):
        from bijectionlens.codec import CodecError, parse_request
        malformed = [
            b'{"version":1,"actual":[],"expected":[],"atol_hex":"0x0.0p+0","limits":{"max_edges":0,"max_edges":1}}',
            b'{"version":1,"actual":[["0X0.0P+0","0x0.0p+0"]],"expected":[],"atol_hex":"0x0.0p+0"}',
        ]
        for value in malformed:
            with self.subTest(value=value), self.assertRaises(CodecError):
                parse_request(value, 'compare')

    def test_serializer_rejects_metaclass_comparison_without_callback(self):
        from bijectionlens import to_dict, ComparisonResult
        class BombMeta(type):
            def __eq__(self, other):
                raise AssertionError('metaclass equality called')
        class Bomb(metaclass=BombMeta):
            pass
        result = ComparisonResult('matched', 0, 0)
        object.__setattr__(result, 'reason', Bomb())
        with self.assertRaises(TypeError):
            to_dict(result)

    def test_worker_protocol_rejects_success_without_certificate_or_verification(self):
        from bijectionlens.cli import main
        source = self.path / 'input.json'
        source.write_text('{"version":1,"actual":[],"expected":[],"atol_hex":"0x0.0p+0"}')
        class Captured:
            def __init__(self):
                self.buffer = io.BytesIO()
            def flush(self):
                pass
        for raw in (b'{"version":1,"kind":"compare","status":"matched"}',
                    b'{"version":1,"kind":"compare","status":"matched","result":{},"verification":{"status":"valid"}}'):
            capture = Captured()
            with patch('bijectionlens.cli.run_request', return_value=raw), patch('sys.stdout', capture):
                code = main(['compare', str(source)])
            self.assertEqual(code, 4)
            self.assertEqual(json.loads(capture.buffer.getvalue())['status'], 'error')

    def test_stdout_failure_is_error_without_retrying_broken_stream(self):
        from bijectionlens.cli import main
        source = self.path / 'input.json'
        source.write_text('{"version":1,"actual":[],"expected":[],"atol_hex":"0x0.0p+0"}')
        class Broken:
            def __init__(self):
                self.buffer = self
                self.calls = 0
            def write(self, value):
                self.calls += 1
                raise BrokenPipeError('closed output')
            def flush(self):
                raise BrokenPipeError('closed output')
        broken = Broken()
        stderr = io.StringIO()
        with patch('sys.stdout', broken), patch('sys.stderr', stderr):
            code = main(['compare', str(source), '--wall-seconds', '0'])
        self.assertEqual(code, 4)
        self.assertEqual(broken.calls, 1)
        self.assertIn('output', stderr.getvalue())
