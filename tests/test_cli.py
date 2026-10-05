"""End-to-end strict JSON and atomic-output behavior."""
import json
import io
import os
from pathlib import Path
import subprocess
import sys

import tempfile
import unittest
from unittest.mock import patch



def request(actual=(0.0,), expected=(0.0,), atol=0.0):
    point = lambda x: [complex(x).real.hex(), complex(x).imag.hex()]
    return {'version': 1, 'actual': [point(x) for x in actual],
            'expected': [point(x) for x in expected], 'atol_hex': float(atol).hex()}


def cli(tmp_path, payload, *args, command='compare'):
    source = tmp_path / 'input.json'
    source.write_text(payload if isinstance(payload, str) else json.dumps(payload))
    env = dict(os.environ)
    result = subprocess.run([sys.executable, '-m', 'bijectionlens', command, str(source), *args],
                            capture_output=True, text=True, env=env, timeout=15)
    return result


def body(result, code):
    assert result.returncode == code, (result.stdout, result.stderr)
    assert result.stderr == ''
    return json.loads(result.stdout)


def test_matched_is_independently_verified_and_deterministic(tmp_path):
    one = cli(tmp_path, request([0, .9], [0, -.9], 1))
    two = cli(tmp_path, request([0, .9], [0, -.9], 1))
    result = body(one, 0)
    assert result['status'] == 'matched'
    assert result['verification']['status'] == 'valid'
    assert one.stdout == two.stdout


INVALID_PAYLOADS = [
    '{"version":1,"version":1,"actual":[],"expected":[],"atol_hex":"0x0.0p+0"}',
    {**request(), 'extra': 0},
    {**request(), 'version': True},
    {**request(), 'atol_hex': '0x1p0'},
    {**request(), 'atol_hex': 'inf'},
    {**request(), 'actual': [['0' * 33, '0x0.0p+0']]},
    {**request(), 'actual': [[0, '0x0.0p+0']]},
    {**request(), 'actual': [['0x0.0p+0']]},
    {**request(), 'actual': 'not a sequence'},
    {**request(), 'limits': {'not_a_limit': 3}},
    '{"version":1,"actual":[],"expected":[],"atol_hex":"0x0.0p+0","limits":{"max_edges":NaN}}',
    '{"version":' + '9' * 3000 + ',"actual":[],"expected":[],"atol_hex":"0x0.0p+0"}',
]
def test_strict_input_rejection(tmp_path, payload):
    assert body(cli(tmp_path, payload), 2)['status'] == 'invalid'


def test_mismatch_and_size_exit_codes(tmp_path):
    assert body(cli(tmp_path, request([0], [2], 0)), 1)['status'] == 'mismatch'
    assert body(cli(tmp_path, request([], [0], 0)), 1)['status'] == 'size_mismatch'


def test_resource_exhaustion_is_inconclusive(tmp_path):
    data = request([0], [0], 0)
    data['limits'] = {'max_edges': 0}
    result = body(cli(tmp_path, data), 3)
    assert result['status'] == 'resource_limited'
    assert result['result']['pairs'] == []


def test_verification_exhaustion_preserves_candidate_without_verified_claim(tmp_path):
    data = request([0], [0], 0)
    data['limits'] = {'max_verify_pairs': 0}
    result = body(cli(tmp_path, data), 3)
    assert result['status'] == 'matched'
    assert result['verification']['status'] == 'resource_limited'


def test_bottleneck_and_verify_roundtrip(tmp_path):
    data = request([0, 3], [0, -1+2.5j])
    del data['atol_hex']
    candidate = body(cli(tmp_path, data, command='bottleneck'), 0)
    assert candidate['status'] == 'optimal'
    replay = {**data, 'kind': 'bottleneck', 'certificate': candidate['result']}
    assert body(cli(tmp_path, replay, command='verify'), 0)['status'] == 'valid'
    replay['certificate']['q_numerator'] = '8'
    assert body(cli(tmp_path, replay, command='verify'), 2)['status'] == 'invalid'


def test_compare_verify_roundtrip_and_unknown_certificate_fields(tmp_path):
    data = request([0, 0, 3], [0, 3, 3], .1)
    candidate = body(cli(tmp_path, data), 1)
    replay = {**data, 'kind': 'compare', 'certificate': candidate['result']}
    assert body(cli(tmp_path, replay, command='verify'), 0)['status'] == 'valid'
    replay['certificate']['unknown'] = True
    assert body(cli(tmp_path, replay, command='verify'), 2)['status'] == 'invalid'


def test_existing_output_is_not_overwritten(tmp_path):
    output = tmp_path / 'result.json'
    output.write_text('original')
    assert body(cli(tmp_path, request(), '--output', str(output)), 4)['status'] == 'error'
    assert output.read_text() == 'original'
    result = cli(tmp_path, request(), '--output', str(output), '--overwrite')
    assert result.returncode == 0 and result.stdout == '' and result.stderr == ''
    assert json.loads(output.read_text())['status'] == 'matched'


def test_input_output_alias_is_refused_even_with_overwrite(tmp_path, alias):
    source = tmp_path / 'input.json'
    source.write_text(json.dumps(request()))
    output = source if alias == 'same' else tmp_path / 'alias.json'
    if alias == 'symlink':
        output.symlink_to(source)
    elif alias == 'hardlink':
        os.link(source, output)
    result = cli(tmp_path, request(), '--output', str(output), '--overwrite')
    assert body(result, 2)['status'] == 'invalid'
    assert json.loads(source.read_text()) == request()


def test_invalid_wall_budget(tmp_path, value):
    assert body(cli(tmp_path, request(), '--wall-seconds', value), 2)['status'] == 'invalid'


def test_zero_wall_budget_is_inconclusive(tmp_path):
    assert body(cli(tmp_path, request(), '--wall-seconds', '0'), 3)['status'] == 'resource_limited'


class CLITests(unittest.TestCase):
    def test_symlink_error_adapter_does_not_hide_unrelated_runtime_errors(self):
        from bijectionlens.cli import _aliases
        with patch('pathlib.Path.resolve', side_effect=RuntimeError('unrelated resolver bug')):
            with self.assertRaisesRegex(RuntimeError, 'unrelated resolver bug'):
                _aliases('input', 'output')

    def test_output_symlink_loop_is_filesystem_error(self):
        loop = self.path / 'loop'
        loop.symlink_to('loop')
        for output in (loop, loop / 'result.json'):
            for overwrite in ([], ['--overwrite']):
                with self.subTest(output=str(output), overwrite=bool(overwrite)):
                    result = cli(self.path, request(), '--output', str(output), *overwrite)
                    self.assertEqual(body(result, 4)['status'], 'error')
        self.assertTrue(loop.is_symlink())
        self.assertEqual(os.readlink(loop), 'loop')

    def test_embedded_nul_path_is_invalid_before_filesystem_calls(self):
        from bijectionlens.cli import main
        source = self.path / 'input.json'
        source.write_text(json.dumps(request()))
        class Captured:
            def __init__(self):
                self.buffer = io.BytesIO()
            def flush(self):
                pass
        for arguments in (['compare', 'invalid\x00path'],
                          ['compare', str(source), '--output', 'invalid\x00path']):
            capture, errors = Captured(), io.StringIO()
            with self.subTest(arguments=repr(arguments)):
                with patch('sys.stdout', capture), patch('sys.stderr', errors):
                    code = main(arguments)
                self.assertEqual(code, 2)
                self.assertEqual(json.loads(capture.buffer.getvalue())['status'], 'invalid')
                self.assertEqual(errors.getvalue(), '')

    def test_stdin_file_alias_is_refused(self):
        source = self.path / 'stdin.json'
        original = json.dumps(request()).encode('ascii')
        source.write_bytes(original)
        with source.open('rb') as stream:
            result = subprocess.run([sys.executable, '-m', 'bijectionlens', 'compare', '-',
                                     '--output', str(source), '--overwrite'],
                                    stdin=stream, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(source.read_bytes(), original)

    def test_documented_json_examples(self):
        examples = Path(__file__).resolve().parents[1] / 'examples'
        for command in ('compare', 'bottleneck'):
            with self.subTest(command=command):
                result = subprocess.run([sys.executable, '-m', 'bijectionlens', command,
                                         str(examples / (command + '.json'))],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
                self.assertEqual(json.loads(result.stdout)['verification']['status'], 'valid')

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)

    def test_strict_input_rejection(self):
        for payload in INVALID_PAYLOADS:
            with self.subTest(payload=str(payload)[:100]):
                test_strict_input_rejection(self.path, payload)

    def test_input_output_alias(self):
        for alias in ('same', 'symlink', 'hardlink'):
            with self.subTest(alias=alias), tempfile.TemporaryDirectory() as directory:
                test_input_output_alias_is_refused_even_with_overwrite(Path(directory), alias)

    def test_invalid_wall_budget(self):
        for value in ('-1', '31', '0.1', 'nan'):
            with self.subTest(value=value):
                test_invalid_wall_budget(self.path, value)


def _case(function):
    def run(self):
        function(self.path)
    run.__name__ = function.__name__
    return run


for _name, _function in list(globals().items()):
    if _name.startswith('test_') and _name not in {
        'test_strict_input_rejection',
        'test_input_output_alias_is_refused_even_with_overwrite',
        'test_invalid_wall_budget',
    }:
        setattr(CLITests, _name, _case(_function))
