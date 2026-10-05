"""Independent, bounded replay of comparison and bottleneck certificates.

No graph-builder, matcher, or optimizer is imported here. Hall neighborhoods are
recomputed against every opposite occurrence in the original inputs. A feasible
matching and an exact Hall shortage prove maximum cardinality; a strict-graph
shortage proves that a bottleneck threshold cannot be lowered.

Only exact result model types or builtin dictionaries are accepted. Nested
containers and integer/string bounds are checked before copying evidence or
performing rational arithmetic. Verification exhaustion is always inconclusive.
"""
from dataclasses import fields
from fractions import Fraction
import math
import sys

from .contract import (Budget, Limits, ResourceLimit, normalize_atol,
                       normalize_points, parse_certificate_decimal)
from .geometry import squared_distance
from .models import (BottleneckResult, ComparisonResult, HallEvidence,
                     ResourceEvidence, VerificationResult)

_MAX_ITEMS = 20_000
_MAX_FIELDS = 64
_MAX_BITS = 64
_MAX_Q_DIGITS = 2_500
_COMMON = frozenset(('status', 'actual_size', 'expected_size', 'pairs', 'counts',
                     'reason', 'resource', 'version', 'verification_status'))
_COMPARISON = _COMMON | {'hall'}
_BOTTLENECK = _COMMON | {'q_numerator', 'q_denominator', 'strict_hall',
                         'approximate_atol', 'least_finite_binary64_atol'}
_HALL = frozenset(('left_indices', 'neighbor_indices', 'deficiency'))
_RESOURCE = frozenset(('phase', 'used', 'requested', 'limit'))
_COUNT_MAXIMA = {field.name.removeprefix('max_'): field.default for field in fields(Limits)}
_PHASES = frozenset(_COUNT_MAXIMA)
_MISSING = object()


class _Invalid(ValueError):
    pass


def _bounded_text(value, name, maximum, optional=False):
    if value is None and optional:
        return
    if type(value) is not str:
        raise _Invalid(name + ' must be a builtin string')
    if len(value) > maximum:
        raise ResourceLimit('certificate_text', 0, len(value), maximum)


def _integer(value, name, maximum=None):
    if type(value) is not int:
        raise _Invalid(name + ' must be a builtin non-bool integer')
    if value.bit_length() > _MAX_BITS:
        raise ResourceLimit('certificate_integer_bits', 0, value.bit_length(), _MAX_BITS)
    if value < 0:
        raise _Invalid(name + ' must be nonnegative')
    if maximum is not None and value > maximum:
        raise ResourceLimit('certificate_items', 0, value, maximum)


def _sequence(value, name, maximum=_MAX_ITEMS):
    if (type(value) is not list and type(value) is not tuple):
        raise _Invalid(name + ' must be a builtin list or tuple')
    if len(value) > maximum:
        raise ResourceLimit('certificate_' + name, 0, len(value), maximum)


def _fields(value, model, allowed, required):
    """Return a safe getter only after rejecting arbitrary objects and keys."""
    if type(value) is model:
        def model_field(key, default=_MISSING):
            try:
                return object.__getattribute__(value, key)
            except AttributeError:
                raise _Invalid('missing certificate model field: ' + key) from None
        return model_field
    if type(value) is not dict:
        raise _Invalid('certificate object has an unsupported type')
    if len(value) > _MAX_FIELDS:
        raise ResourceLimit('certificate_fields', 0, len(value), _MAX_FIELDS)
    # Never test membership or perform a dictionary lookup until every stored
    # key is a builtin string; hostile key equality must not be callable here.
    for key in value:
        _bounded_text(key, 'field name', 64)
    for key in value:
        if key not in allowed:
            raise _Invalid('unknown certificate field: ' + key)
    for key in required:
        if key not in value:
            raise _Invalid('missing certificate field: ' + key)
    return value.get


def _check_pairs(pairs):
    _sequence(pairs, 'pairs')
    for pair in pairs:
        _sequence(pair, 'pair')
        if len(pair) != 2:
            raise _Invalid('every pair must have exactly two indices')
        _integer(pair[0], 'left pair index')
        _integer(pair[1], 'right pair index')


def _check_hall(value):
    if value is None:
        return None
    get = _fields(value, HallEvidence, _HALL, _HALL)
    left = get('left_indices')
    right = get('neighbor_indices')
    # Check both lengths before walking either side.
    _sequence(left, 'left_indices')
    _sequence(right, 'neighbor_indices')
    for index in left:
        _integer(index, 'Hall left index')
    for index in right:
        _integer(index, 'Hall neighbor index')
    deficiency = get('deficiency')
    _integer(deficiency, 'Hall deficiency')
    return left, right, deficiency


def _check_counts(value):
    if type(value) is dict:
        if len(value) > len(_PHASES):
            raise ResourceLimit('certificate_counts', 0, len(value), len(_PHASES))
        items = value.items()
    else:
        _sequence(value, 'counts', len(_PHASES))
        items = value
    names = set()
    for entry in items:
        _sequence(entry, 'count')
        if len(entry) != 2:
            raise _Invalid('counts must contain name/integer pairs')
        name, count = entry
        _bounded_text(name, 'counter name', 64)
        if name not in _PHASES or name in names:
            raise _Invalid('counter names must be known and unique')
        _integer(count, 'counter')
        if count > _COUNT_MAXIMA[name]:
            raise _Invalid('reported counter exceeds its hard phase maximum')
        names.add(name)


def _check_resource(value):
    if value is None:
        return
    get = _fields(value, ResourceEvidence, _RESOURCE, _RESOURCE)
    phase = get('phase')
    _bounded_text(phase, 'resource phase', 64)
    if not phase:
        raise _Invalid('resource phase must not be empty')
    for name in ('used', 'requested', 'limit'):
        _integer(get(name), 'resource ' + name)


def _decimal(value, name):
    _bounded_text(value, name, _MAX_Q_DIGITS)
    return parse_certificate_decimal(value)


def _certificate(result, bottleneck=False):
    model = BottleneckResult if bottleneck else ComparisonResult
    allowed = _BOTTLENECK if bottleneck else _COMPARISON
    get = _fields(result, model, allowed, ('status', 'actual_size', 'expected_size'))
    status = get('status')
    _bounded_text(status, 'status', 32)
    choices = {'optimal', 'size_mismatch', 'resource_limited'} if bottleneck else {
        'matched', 'mismatch', 'size_mismatch', 'resource_limited'}
    if status not in choices:
        raise _Invalid('unknown certificate status')
    actual_size, expected_size = get('actual_size'), get('expected_size')
    _integer(actual_size, 'actual_size', _MAX_ITEMS)
    _integer(expected_size, 'expected_size', _MAX_ITEMS)
    version = get('version', 1)
    _integer(version, 'version')
    if version != 1:
        raise _Invalid('only certificate version 1 is supported')
    verification_status = get('verification_status', 'not_run')
    _bounded_text(verification_status, 'verification_status', 32)
    if verification_status != 'not_run':
        raise _Invalid('solver certificates must not claim independent verification')
    reason = get('reason', None)
    _bounded_text(reason, 'reason', 4096, optional=True)
    pairs = get('pairs', ())
    hall_value = get('strict_hall' if bottleneck else 'hall', None)
    # Top-level container bounds are checked before traversing their contents.
    _sequence(pairs, 'pairs')
    hall = _check_hall(hall_value)
    _check_counts(get('counts', ()))
    _check_resource(get('resource', None))
    _check_pairs(pairs)
    _index_ranges(pairs, hall, actual_size, expected_size)
    data = dict(status=status, actual_size=actual_size, expected_size=expected_size,
                pairs=pairs, hall=hall)
    if bottleneck:
        numerator = get('q_numerator', None)
        denominator = get('q_denominator', None)
        approximate = get('approximate_atol', None)
        least = get('least_finite_binary64_atol', None)
        _bounded_text(approximate, 'approximate_atol', 128, optional=True)
        _bounded_text(least, 'least_finite_binary64_atol', 32, optional=True)
        if approximate is not None and not approximate.isascii():
            raise _Invalid('approximate_atol must be ASCII text')
        # Check both lengths before parsing either integer.
        _bounded_text(numerator, 'q_numerator', _MAX_Q_DIGITS, optional=True)
        _bounded_text(denominator, 'q_denominator', _MAX_Q_DIGITS, optional=True)
        q_parts = None
        if numerator is not None or denominator is not None:
            num = _decimal(numerator, 'q_numerator')
            den = _decimal(denominator, 'q_denominator')
            if den == 0:
                raise _Invalid('q denominator must be positive')
            q_parts = num, den
        data.update(q_parts=q_parts, least=least, approximate=approximate)
    return data


def _index_ranges(pairs, hall, actual_size, expected_size):
    """Reject all malformed index evidence before any distance arithmetic."""
    left_seen, right_seen = set(), set()
    for i, j in pairs:
        if i >= actual_size or j >= expected_size:
            raise _Invalid('pair index outside certificate sizes')
        if i in left_seen or j in right_seen:
            raise _Invalid('matching repeats an occurrence')
        left_seen.add(i)
        right_seen.add(j)
    if hall is not None:
        left, right, deficiency = hall
        if any(i >= actual_size for i in left) or any(j >= expected_size for j in right):
            raise _Invalid('Hall index outside certificate sizes')
        if len(set(left)) != len(left) or len(set(right)) != len(right):
            raise _Invalid('Hall indices must not repeat')
        if deficiency <= 0 or len(left) - len(right) != deficiency:
            raise _Invalid('Hall deficiency is not a positive exact shortage')


def _input_shapes(actual, expected, limits):
    """Bound both original collections before normalizing either one."""
    for values in (actual, expected):
        if type(values) is not list and type(values) is not tuple:
            raise _Invalid('original inputs must be builtin lists or tuples')
    for values in (actual, expected):
        if len(values) > limits.max_items:
            raise ResourceLimit('items', 0, len(values), limits.max_items)


def _sizes(data, actual, expected):
    if data['actual_size'] != len(actual) or data['expected_size'] != len(expected):
        raise _Invalid('certificate sizes disagree with original inputs')


def _pair_feasibility(pairs, actual, expected, threshold, budget):
    left_seen, right_seen = set(), set()
    for i, j in pairs:
        if i >= len(actual) or j >= len(expected):
            raise _Invalid('pair index outside original inputs')
        if i in left_seen or j in right_seen:
            raise _Invalid('matching repeats an occurrence')
        left_seen.add(i)
        right_seen.add(j)
        budget.charge('verify_pairs')
        if squared_distance(actual[i], expected[j]) > threshold:
            raise _Invalid('matching includes a pair beyond the threshold')


def _hall_shortage(hall, actual, expected, threshold, budget, strict=False):
    if hall is None:
        raise _Invalid('a Hall shortage certificate is required')
    left, claimed, deficiency = hall
    if len(set(left)) != len(left) or len(set(claimed)) != len(claimed):
        raise _Invalid('Hall indices must not repeat')
    if any(i >= len(actual) for i in left) or any(j >= len(expected) for j in claimed):
        raise _Invalid('Hall index outside original inputs')
    if deficiency <= 0 or len(left) - len(claimed) != deficiency:
        raise _Invalid('Hall deficiency is not a positive exact shortage')
    neighbors = set()
    for i in left:
        for j, point in enumerate(expected):
            budget.charge('verify_pairs')
            distance = squared_distance(actual[i], point)
            if distance < threshold if strict else distance <= threshold:
                neighbors.add(j)
    if neighbors != set(claimed):
        raise _Invalid('Hall evidence does not list the complete original neighborhood')
    return deficiency


def _least_tolerance(least, threshold):
    if threshold == 0:
        if least != '0x0.0p+0':
            raise _Invalid('zero threshold requires positive-zero least tolerance')
        return
    if least is None:
        maximum = Fraction.from_float(sys.float_info.max)
        if maximum * maximum >= threshold:
            raise _Invalid('a finite binary64 tolerance exists but is omitted')
        return
    if not least.isascii():
        raise _Invalid('least tolerance must use canonical binary64 hex')
    try:
        value = float.fromhex(least)
    except (ValueError, OverflowError):
        raise _Invalid('least tolerance must use canonical binary64 hex') from None
    if not math.isfinite(value) or value <= 0 or value.hex() != least:
        raise _Invalid('least tolerance must use canonical positive finite binary64 hex')
    exact = Fraction.from_float(value)
    predecessor = Fraction.from_float(math.nextafter(value, 0.0))
    if exact * exact < threshold or predecessor * predecessor >= threshold:
        raise _Invalid('claimed binary64 tolerance is not the least sufficient value')


def _outcome(status, reason, budget):
    return VerificationResult(status, reason, budget.snapshot() if budget is not None else ())


def verify_comparison(actual, expected, *, atol, result, limits=None):
    """Return valid, invalid, or resource_limited without trusting solver work.

    ``result`` must be exactly ComparisonResult or a builtin dictionary with
    its schema. Original values obey the same bounded binary64 contract as the
    comparator. Validity attests the mathematical comparison certificate.
    Reported counters are schema-checked, not proof of actual solver execution.
    """
    budget = None
    try:
        data = _certificate(result)
        budget = Budget(limits)
        _input_shapes(actual, expected, budget.limits)
        left = normalize_points(actual, budget.limits)
        right = normalize_points(expected, budget.limits)
        tolerance = normalize_atol(atol)
        threshold = tolerance * tolerance
        _sizes(data, left, right)
        if data['status'] == 'resource_limited':
            if data['pairs'] or data['hall'] is not None:
                raise _Invalid('resource-limited candidate must not claim a numerical proof')
            return _outcome('resource_limited', 'candidate reports resource exhaustion', budget)
        if data['status'] == 'size_mismatch':
            if len(left) == len(right) or data['pairs'] or data['hall'] is not None:
                raise _Invalid('invalid size mismatch certificate')
            return _outcome('valid', 'original input lengths differ', budget)
        if len(left) != len(right):
            raise _Invalid('numerical comparison certificate requires equal sizes')
        pairs = data['pairs']
        _pair_feasibility(pairs, left, right, threshold, budget)
        if data['status'] == 'matched':
            if len(pairs) != len(left) or data['hall'] is not None:
                raise _Invalid('matched result requires a full bijection and no shortage')
        else:
            if len(pairs) >= len(left):
                raise _Invalid('mismatch requires a partial matching')
            deficiency = _hall_shortage(data['hall'], left, right, threshold, budget)
            if deficiency != len(left) - len(pairs):
                raise _Invalid('Hall shortage does not prove the claimed maximum cardinality')
        return _outcome('valid', 'certificate independently verified from original inputs', budget)
    except ResourceLimit as error:
        return _outcome('resource_limited', str(error), budget)
    except (TypeError, ValueError) as error:
        return _outcome('invalid', str(error), budget)


def verify_bottleneck(actual, expected, *, result, limits=None):
    """Replay a full matching at q and an all-neighbor strict Hall proof below q.

    Validity attests the exact squared optimum and least binary64 tolerance.
    It does not attest the approximate display or reported execution counters.
    """
    budget = None
    try:
        data = _certificate(result, bottleneck=True)
        budget = Budget(limits)
        _input_shapes(actual, expected, budget.limits)
        left = normalize_points(actual, budget.limits)
        right = normalize_points(expected, budget.limits)
        _sizes(data, left, right)
        if data['status'] in {'resource_limited', 'size_mismatch'}:
            if (data['pairs'] or data['hall'] is not None or data['q_parts'] is not None
                    or data['least'] is not None or data['approximate'] is not None):
                raise _Invalid('non-optimal result must not claim a bottleneck threshold')
            if data['status'] == 'resource_limited':
                return _outcome('resource_limited', 'candidate reports resource exhaustion', budget)
            if len(left) == len(right):
                raise _Invalid('size mismatch certificate requires unequal original sizes')
            return _outcome('valid', 'original input lengths differ', budget)
        if len(left) != len(right) or len(data['pairs']) != len(left):
            raise _Invalid('optimal result requires equal sizes and a full matching')
        if data['q_parts'] is None:
            raise _Invalid('optimal result must include a squared threshold')
        numerator, denominator = data['q_parts']
        if math.gcd(numerator, denominator) != 1:
            raise _Invalid('squared threshold must be a reduced rational')
        threshold = Fraction(numerator, denominator)
        _pair_feasibility(data['pairs'], left, right, threshold, budget)
        if threshold > 0:
            _hall_shortage(data['hall'], left, right, threshold, budget, strict=True)
        elif data['hall'] is not None:
            raise _Invalid('zero threshold has its lower bound by nonnegativity')
        _least_tolerance(data['least'], threshold)
        return _outcome('valid', 'exact squared optimum independently verified', budget)
    except ResourceLimit as error:
        return _outcome('resource_limited', str(error), budget)
    except (TypeError, ValueError) as error:
        return _outcome('invalid', str(error), budget)
