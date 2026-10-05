"""Small, non-executable v1 JSON codec with explicit pre-parse bounds."""
from __future__ import annotations

import json
import math

INPUT_BYTES = 8 * 1024 * 1024
RESULT_BYTES = 32 * 1024 * 1024
VERIFY_BYTES = INPUT_BYTES + RESULT_BYTES
MAX_ITEMS = 20_000
MAX_DEPTH = 16


class CodecError(ValueError):
    """Malformed bounded input."""


class CodecLimit(ValueError):
    """Input could not be examined within a declared bound."""


def read_bounded(stream, limit=INPUT_BYTES):
    """Read at most limit+1 bytes, without consuming an oversized stream."""
    data = stream.read(limit + 1)
    if type(data) is not bytes:
        raise CodecError('input stream must be binary')
    if len(data) > limit:
        raise CodecLimit('JSON byte limit exceeded')
    return data


def _preflight(text):
    # Bound depth, keys and object members before json builds their containers.
    stack = []
    quoted = escaped = False
    string_start = 0
    for index, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            if index - string_start > 8192:
                raise CodecLimit('JSON string limit exceeded')
            continue
        if char == '"':
            quoted = True
            string_start = index
        elif char in '[{':
            stack.append([char, 0])
            if len(stack) > MAX_DEPTH:
                raise CodecError('JSON nesting is too deep')
        elif char in ']}':
            if stack:
                stack.pop()
        elif char == ',' and stack:
            stack[-1][1] += 1
            if stack[-1][0] == '{' and stack[-1][1] >= 64:
                raise CodecError('too many object fields')
    if quoted:
        raise CodecError('unterminated JSON string')


def _object(pairs):
    if len(pairs) > 64:
        raise CodecError('too many object fields')
    result = {}
    for key, value in pairs:
        if len(key) > 64 or key in result:
            raise CodecError('duplicate or overlong JSON field')
        result[key] = value
    return result


def _integer(value):
    if len(value.lstrip('-')) > 20:
        raise CodecError('JSON integer exceeds 64-bit bound')
    answer = int(value)
    if abs(answer).bit_length() > 64:
        raise CodecError('JSON integer exceeds 64-bit bound')
    return answer


def _no_float(value):
    raise CodecError('JSON numbers must be bounded integers; coordinates use hex strings')


def loads_bounded(data, max_bytes=INPUT_BYTES):
    if type(data) is not bytes:
        raise CodecError('JSON input must be bytes')
    if len(data) > max_bytes:
        raise CodecLimit('JSON byte limit exceeded')
    try:
        text = data.decode('utf-8')
        _preflight(text)
        return json.loads(text, object_pairs_hook=_object, parse_int=_integer,
                          parse_float=_no_float, parse_constant=_no_float)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise CodecError('invalid UTF-8 JSON') from error


def _fields(value, required, optional=()):
    if type(value) is not dict:
        raise CodecError('expected a JSON object')
    keys = set(value)
    if keys - set(required) - set(optional) or set(required) - keys:
        raise CodecError('unknown or missing JSON field')


def _hex(value):
    if type(value) is not str or len(value) > 32 or not value.isascii():
        raise CodecError('coordinate must be a canonical finite float.hex string')
    try:
        number = float.fromhex(value)
    except (ValueError, OverflowError) as error:
        raise CodecError('malformed hexadecimal binary64 value') from error
    if not math.isfinite(number) or number.hex() != value:
        raise CodecError('noncanonical or nonfinite hexadecimal binary64 value')
    return number


def _points(value):
    if type(value) is not list:
        raise CodecError('point collection must be an array')
    if len(value) > MAX_ITEMS:
        raise CodecLimit('point count exceeds hard maximum')
    points = []
    for pair in value:
        if type(pair) is not list or len(pair) != 2:
            raise CodecError('each point must have exactly two hexadecimal coordinates')
        points.append(complex(_hex(pair[0]), _hex(pair[1])))
    return tuple(points)


COMPARE_FIELDS = ('status', 'actual_size', 'expected_size', 'pairs', 'hall', 'counts',
                  'reason', 'resource', 'version', 'verification_status')
BOTTLENECK_FIELDS = ('status', 'actual_size', 'expected_size', 'q_numerator',
                     'q_denominator', 'pairs', 'strict_hall', 'approximate_atol',
                     'least_finite_binary64_atol', 'counts', 'reason', 'resource',
                     'version', 'verification_status')


def _certificate_shape(value, kind):
    fields = COMPARE_FIELDS if kind == 'compare' else BOTTLENECK_FIELDS
    _fields(value, ('status', 'actual_size', 'expected_size'), fields)
    for key in ('hall', 'strict_hall'):
        if key in value and value[key] is not None:
            _fields(value[key], ('left_indices', 'neighbor_indices', 'deficiency'))
    if value.get('resource') is not None:
        _fields(value['resource'], ('phase', 'used', 'requested', 'limit'))
    if len(_dump(value)) > RESULT_BYTES:
        raise CodecLimit('certificate exceeds result byte maximum')


def _verify_raw_bounds(data):
    """Bound each raw top-level component before parsing the JSON document."""
    depth = 0
    quoted = escaped = False
    key_start = None
    key = None
    value_start = None
    certificate_bytes = 0
    for index, char in enumerate(data):
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
                if key_start is not None:
                    raw_key = data[key_start:index]
                    if len(raw_key) > 64 or b'\\' in raw_key or not raw_key.isascii():
                        raise CodecError('field names must be short literal ASCII strings')
                    key = raw_key
                    key_start = None
            continue
        if char == 34:
            quoted = True
            if depth == 1 and value_start is None:
                key_start = index + 1
        elif char == 58 and depth == 1:
            value_start = index + 1
        elif (char == 44 or char == 125) and depth == 1:
            if key == b'certificate' and value_start is not None:
                component = index - value_start
                if component > RESULT_BYTES:
                    raise CodecLimit('raw certificate byte limit exceeded')
                certificate_bytes += component
            key = None
            value_start = None
            if char == 125:
                depth -= 1
        elif char == 123 or char == 91:
            depth += 1
            if depth > MAX_DEPTH:
                raise CodecError('JSON nesting is too deep')
        elif char == 125 or char == 93:
            depth -= 1
    original_bytes = len(data) - certificate_bytes
    if original_bytes > INPUT_BYTES:
        raise CodecLimit('original input/envelope byte limit exceeded')
    return original_bytes


def parse_request(data, command):
    """Validate and normalize a concrete JSON request, never loading code."""
    from .contract import Limits
    maximum = VERIFY_BYTES if command == 'verify' else INPUT_BYTES
    if type(data) is not bytes:
        raise CodecError('JSON input must be bytes')
    if len(data) > maximum:
        raise CodecLimit('JSON byte limit exceeded')
    original_bytes = _verify_raw_bounds(data) if command == 'verify' else len(data)
    value = loads_bounded(data, maximum)
    if command not in ('compare', 'bottleneck', 'verify'):
        raise CodecError('unknown command')
    required = ['version', 'actual', 'expected']
    if command == 'verify':
        required += ['kind', 'certificate']
        kind = value.get('kind') if type(value) is dict else None
        if kind not in ('compare', 'bottleneck'):
            raise CodecError('unknown certificate kind')
    else:
        kind = command
    if kind == 'compare':
        required += ['atol_hex']
    _fields(value, required, ('limits',))
    if type(value['version']) is not int or value['version'] != 1:
        raise CodecError('unsupported schema version')
    supplied_limits = value.get('limits', {})
    if type(supplied_limits) is not dict:
        raise CodecError('limits must be an object')
    try:
        limits = Limits(**supplied_limits)
    except (TypeError, ValueError) as error:
        raise CodecError('invalid resource limits') from error
    if original_bytes > limits.max_input_bytes:
        raise CodecLimit('input exceeds configured byte limit')
    actual_raw, expected_raw = value['actual'], value['expected']
    for points in (actual_raw, expected_raw):
        if type(points) is list and len(points) > limits.max_items:
            raise CodecLimit('point count exceeds configured limit')
    result = {'command': command, 'kind': kind, 'actual': _points(actual_raw),
              'expected': _points(expected_raw), 'limits': supplied_limits}
    if kind == 'compare':
        tolerance = _hex(value['atol_hex'])
        if tolerance < 0:
            raise CodecError('tolerance must be nonnegative')
        result['atol'] = tolerance
    if command == 'verify':
        _certificate_shape(value['certificate'], kind)
        result['certificate'] = value['certificate']
    return result


def _safe(value):
    typ = type(value)
    if value is None or typ is str or typ is int or typ is bool:
        return value
    if typ is tuple or typ is list:
        if len(value) > MAX_ITEMS:
            raise CodecLimit('result collection exceeds hard maximum')
        return [_safe(item) for item in value]
    from .models import HallEvidence, ResourceEvidence
    if type(value) is HallEvidence:
        fields = ('left_indices', 'neighbor_indices', 'deficiency')
    elif type(value) is ResourceEvidence:
        fields = ('phase', 'used', 'requested', 'limit')
    else:
        raise TypeError('only exact builtin values and known evidence models can be serialized')
    return {field: _safe(object.__getattribute__(value, field)) for field in fields}


def to_dict(result):
    """Export only known result types; do not invoke user serialization hooks."""
    from .models import ComparisonResult, BottleneckResult, VerificationResult
    if type(result) is ComparisonResult:
        fields = COMPARE_FIELDS
    elif type(result) is BottleneckResult:
        fields = BOTTLENECK_FIELDS
    elif type(result) is VerificationResult:
        fields = ('status', 'reason', 'counts', 'version')
    else:
        raise TypeError('expected an exact BijectionLens result model')
    return {field: _safe(object.__getattribute__(result, field)) for field in fields}


def _dump(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                       allow_nan=False) + '\n').encode('ascii')


def dumps_bounded(value, max_bytes=RESULT_BYTES):
    data = _dump(value)
    if len(data) > max_bytes:
        raise CodecLimit('serialized result byte limit exceeded')
    return data
