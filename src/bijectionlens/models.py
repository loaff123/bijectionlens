"""Immutable bounded certificate models.

Construction checks representation shape, not mathematical certificate truth.
The independent verifier establishes correctness against original inputs.
"""
from dataclasses import dataclass
from .contract import ResourceLimit

_MAX_ITEMS = 20_000
_MAX_COUNT_FIELDS = 64
_MAX_INTEGER = (1 << 64) - 1


def _integer(value, name, maximum=_MAX_INTEGER):
    if type(value) is not int:
        raise TypeError(f'{name} must be a builtin integer')
    if not 0 <= value <= maximum:
        raise ValueError(f'{name} is outside its bounded nonnegative range')
    return value


def _text(value, name, maximum=4096, optional=False):
    if value is None and optional:
        return None
    if type(value) is not str:
        raise TypeError(f'{name} must be a builtin string')
    if len(value) > maximum:
        raise ResourceLimit('certificate_text', 0, len(value), maximum)
    return value


def _sequence(value, name, maximum=_MAX_ITEMS):
    if (type(value) is not list and type(value) is not tuple):
        raise TypeError(f'{name} must be a builtin list or tuple')
    if len(value) > maximum:
        raise ResourceLimit('certificate_' + name, 0, len(value), maximum)
    return value


def _indices(value, name):
    _sequence(value, name)
    return tuple(_integer(item, name) for item in value)


def _pairs(value):
    _sequence(value, 'pairs')
    result = []
    for pair in value:
        if (type(pair) is not list and type(pair) is not tuple):
            raise TypeError('each pair must be a builtin list or tuple')
        if len(pair) != 2:
            raise ValueError('each pair must contain exactly two indices')
        result.append((_integer(pair[0], 'pair index'), _integer(pair[1], 'pair index')))
    return tuple(result)


def _counts(value):
    if type(value) is dict:
        if len(value) > _MAX_COUNT_FIELDS:
            raise ResourceLimit('certificate_counts', 0, len(value), _MAX_COUNT_FIELDS)
        items = value.items()
    else:
        items = _sequence(value, 'counts', _MAX_COUNT_FIELDS)
    result = []
    names = set()
    for item in items:
        if (type(item) is not list and type(item) is not tuple) or len(item) != 2:
            raise TypeError('counts must contain name/integer pairs')
        name, count = item
        _text(name, 'count name', 64)
        if not name or name in names:
            raise ValueError('count names must be nonempty and unique')
        names.add(name)
        result.append((name, _integer(count, 'count')))
    return tuple(sorted(result))


def _status(value, choices):
    _text(value, 'status', 32)
    if value not in choices:
        raise ValueError('unknown result status')


def _common(result):
    size_limit = _MAX_INTEGER if result.status == 'resource_limited' else _MAX_ITEMS
    _integer(result.actual_size, 'actual_size', size_limit)
    _integer(result.expected_size, 'expected_size', size_limit)
    _integer(result.version, 'version', 1)
    if result.version != 1:
        raise ValueError('only version 1 is supported')
    if type(result.verification_status) is not str or result.verification_status != 'not_run':
        raise ValueError('solver models cannot claim independent verification')
    _text(result.reason, 'reason', optional=True)
    if result.resource is not None and type(result.resource) is not ResourceEvidence:
        raise TypeError('resource must be ResourceEvidence or None')
    object.__setattr__(result, 'pairs', _pairs(result.pairs))
    object.__setattr__(result, 'counts', _counts(result.counts))


class _NoTruthValue:
    __slots__ = ()

    def __bool__(self):
        raise TypeError('inspect the explicit status; results have no truth value')


@dataclass(frozen=True, slots=True)
class ResourceEvidence:
    phase: str
    used: int
    requested: int
    limit: int

    def __post_init__(self):
        _text(self.phase, 'phase', 64)
        if not self.phase:
            raise ValueError('phase must be nonempty')
        for name in ('used', 'requested', 'limit'):
            _integer(getattr(self, name), name)

    @classmethod
    def from_error(cls, error):
        if type(error) is not ResourceLimit:
            raise TypeError('error must be ResourceLimit')
        return cls(error.phase, error.used, error.requested, error.limit)


@dataclass(frozen=True, slots=True)
class HallEvidence:
    left_indices: tuple[int, ...]
    neighbor_indices: tuple[int, ...]
    deficiency: int

    def __post_init__(self):
        # Check both lengths before converting either collection.
        _sequence(self.left_indices, 'left_indices')
        _sequence(self.neighbor_indices, 'neighbor_indices')
        object.__setattr__(self, 'left_indices', _indices(self.left_indices, 'left_indices'))
        object.__setattr__(self, 'neighbor_indices', _indices(self.neighbor_indices, 'neighbor_indices'))
        _integer(self.deficiency, 'deficiency', _MAX_ITEMS)


@dataclass(frozen=True, slots=True)
class ComparisonResult(_NoTruthValue):
    status: str
    actual_size: int
    expected_size: int
    pairs: tuple[tuple[int, int], ...] = ()
    hall: HallEvidence | None = None
    counts: tuple[tuple[str, int], ...] = ()
    reason: str | None = None
    resource: ResourceEvidence | None = None
    version: int = 1
    verification_status: str = 'not_run'

    def __post_init__(self):
        _status(self.status, {'matched', 'mismatch', 'size_mismatch', 'resource_limited'})
        _common(self)
        if self.hall is not None and type(self.hall) is not HallEvidence:
            raise TypeError('hall must be HallEvidence or None')
        if self.status == 'resource_limited' and (self.pairs or self.hall is not None):
            raise ValueError('resource_limited results cannot claim a matching or Hall certificate')


@dataclass(frozen=True, slots=True)
class BottleneckResult(_NoTruthValue):
    status: str
    actual_size: int
    expected_size: int
    q_numerator: str | None = None
    q_denominator: str | None = None
    pairs: tuple[tuple[int, int], ...] = ()
    strict_hall: HallEvidence | None = None
    approximate_atol: str | None = None
    least_finite_binary64_atol: str | None = None
    counts: tuple[tuple[str, int], ...] = ()
    reason: str | None = None
    resource: ResourceEvidence | None = None
    version: int = 1
    verification_status: str = 'not_run'

    def __post_init__(self):
        _status(self.status, {'optimal', 'size_mismatch', 'resource_limited'})
        _common(self)
        _text(self.q_numerator, 'q_numerator', 2500, optional=True)
        _text(self.q_denominator, 'q_denominator', 2500, optional=True)
        _text(self.approximate_atol, 'approximate_atol', 128, optional=True)
        _text(self.least_finite_binary64_atol, 'least_finite_binary64_atol', 32, optional=True)
        if self.strict_hall is not None and type(self.strict_hall) is not HallEvidence:
            raise TypeError('strict_hall must be HallEvidence or None')
        if self.status == 'resource_limited' and (self.pairs or self.strict_hall is not None
                or self.q_numerator is not None or self.q_denominator is not None
                or self.approximate_atol is not None or self.least_finite_binary64_atol is not None):
            raise ValueError('resource_limited results cannot claim an optimum')


@dataclass(frozen=True, slots=True)
class VerificationResult(_NoTruthValue):
    status: str
    reason: str = ''
    counts: tuple[tuple[str, int], ...] = ()
    version: int = 1

    def __post_init__(self):
        _status(self.status, {'valid', 'invalid', 'resource_limited'})
        _text(self.reason, 'reason')
        _integer(self.version, 'version', 1)
        if self.version != 1:
            raise ValueError('only version 1 is supported')
        object.__setattr__(self, 'counts', _counts(self.counts))
