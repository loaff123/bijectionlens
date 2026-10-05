"""Independent numerical review, no prototype imports or copied oracle.

Integer oracle decodes IEEE754 bits onto a 2**-1074 lattice.
Matching oracle enumerates minimum vertex covers (Konig's theorem).
"""
import dataclasses
from fractions import Fraction
import hashlib
import importlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import struct
import sys
import time

ROOT = Path(os.environ.get('BIJECTIONLENS_SOURCE', str(Path(__file__).resolve().parents[2] / 'bijectionlens'))).resolve()
SRC = ROOT / 'src' / 'bijectionlens'
# Final review exercises the real package initializer as well as core modules.
sys.path.insert(0, str(SRC.parent))
from bijectionlens.contract import normalize_points, normalize_atol, Limits, Budget, ResourceLimit
from bijectionlens.geometry import squared_distance, box_squared_distance
from bijectionlens.spatial import radius_graph
from bijectionlens.matching import maximum_matching, hall_shortage
from bijectionlens.compare import compare
from bijectionlens.models import ComparisonResult, BottleneckResult, HallEvidence, ResourceEvidence

REPORT = {'runtime': sys.version, 'checks': {}, 'failures': []}
def hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(SRC.glob('*.py'))}
REPORT['before'] = hashes()

def run(name, f):
    started = time.monotonic()
    try:
        detail = f()
        REPORT['checks'][name] = {'status':'passed', 'seconds': time.monotonic()-started, 'detail':detail}
    except Exception as e:
        import traceback
        REPORT['checks'][name] = {'status':'failed', 'seconds': time.monotonic()-started, 'error': repr(e), 'traceback':traceback.format_exc()}
        REPORT['failures'].append(name)
    print(name, REPORT['checks'][name]['status'], flush=True)

def units(x):
    """Decode exact binary64 value into integer subnormal units."""
    bits = struct.unpack('>Q', struct.pack('>d', x))[0]
    exp, mant = (bits >> 52) & 2047, bits & ((1 << 52)-1)
    assert exp != 2047
    mag = mant if exp == 0 else ((1 << 52) | mant) << (exp - 1)
    return -mag if bits >> 63 else mag

def coord(z):
    if type(z) is complex:
        return units(z.real), units(z.imag)
    return units(float(z)), 0

def distance_units(a, b):
    ar, ai = coord(a); br, bi = coord(b)
    return (ar-br)**2 + (ai-bi)**2

def within(a, b, t):
    return distance_units(a,b) <= units(float(t))**2

def oracle_card(graph, nright):
    # Every cover is a subset A of left plus all neighbors of left \ A.
    # Its minimum cardinality equals the maximum matching cardinality.
    answer = min(len(graph), nright)
    for cover in range(1 << len(graph)):
        needed = 0
        for i, row in enumerate(graph):
            if not cover & (1 << i):
                for j in row: needed |= 1 << j
        answer = min(answer, cover.bit_count() + needed.bit_count())
    return answer

def check_matching(graph, nr):
    budget = Budget()
    m = maximum_matching(graph, nr, budget)
    assert m.cardinality == oracle_card(graph, nr), (graph, m)
    pairs = m.pairs
    assert len({i for i,j in pairs}) == len(pairs) == len({j for i,j in pairs})
    for i,j in pairs:
        assert j in graph[i] and m.left[i] == j and m.right[j] == i
    assert all(i == -1 or m.left[i] == j for j,i in enumerate(m.right))
    if m.cardinality < len(graph):
        h = hall_shortage(graph, m, budget)
        assert set(h.neighbor_indices) == set(itertools.chain.from_iterable(graph[i] for i in h.left_indices))
        assert h.deficiency == len(h.left_indices)-len(h.neighbor_indices) == len(graph)-m.cardinality
    return m

def exhaustive_graphs():
    total=0
    for n in range(5):
        for mask in range(1 << n*n):
            graph=tuple(tuple(j for j in range(n) if mask & (1 << (i*n+j))) for i in range(n))
            check_matching(graph,n); total+=1
    assert total == 66067
    return {'graphs':total,'oracle':'minimum vertex cover exhaustive left subsets'}

def random_rectangular():
    rng=random.Random(50786711)
    for _ in range(1500):
        nl,nr=rng.randrange(11),rng.randrange(11)
        graph=tuple(tuple(j for j in range(nr) if rng.randrange(3)==0) for i in range(nl))
        check_matching(graph,nr)
    return {'graphs':1500}

def long_paths():
    n=20000
    graph=tuple((i,i+1) for i in range(n-1))+((0,),)
    budget=Budget()
    m=maximum_matching(graph,n,budget)
    assert m.cardinality == n and m.left == tuple(range(1,n))+(0,)
    # Remove the last available right: an alternating shortage reaches all left.
    graph=tuple((i,i+1) for i in range(n-2))+((n-2,), (0,))
    budget2=Budget(); m2=maximum_matching(graph,n,budget2)
    h=hall_shortage(graph,m2,budget2)
    assert m2.cardinality==n-1 and h.left_indices==tuple(range(n)) and h.neighbor_indices==tuple(range(n-1)) and h.deficiency==1
    return {'vertices_each_side':n,'perfect_counts':dict(budget.snapshot()),'hall_counts':dict(budget2.snapshot())}

def finite(rng):
    bits=rng.getrandbits(64)
    if (bits >>52)&2047 == 2047: bits ^= 1 << 52
    return struct.unpack('>d',struct.pack('>Q',bits))[0]

def geometry_checks():
    rng=random.Random(572938100)
    special=[0., -0., 5e-324, -5e-324, sys.float_info.min, -sys.float_info.min, sys.float_info.max, -sys.float_info.max,1.,math.nextafter(1.,0),math.nextafter(1.,math.inf)]
    def number(): return rng.choice(special) if rng.randrange(4)==0 else finite(rng)
    count=12000
    for _ in range(count):
        a,b=complex(number(),number()),complex(number(),number()); t=abs(number())
        p,q=normalize_points([a,b]); d=squared_distance(p,q)
        integer_distance=distance_units(a,b)
        assert d.numerator*(1<<2148)==integer_distance*d.denominator
        assert (d <= normalize_atol(t)**2) == within(a,b,t)
    boxes=2500
    for _ in range(boxes):
        vals=[number() for _ in range(6)]
        lo_r,hi_r=sorted(vals[:2]); lo_i,hi_i=sorted(vals[2:4]); p=complex(*vals[4:])
        bounds=tuple(Fraction.from_float(x) for x in (lo_r,hi_r,lo_i,hi_i))
        dx=0 if lo_r <= p.real <= hi_r else min(abs(units(p.real)-units(lo_r)),abs(units(p.real)-units(hi_r)))
        dy=0 if lo_i <= p.imag <= hi_i else min(abs(units(p.imag)-units(lo_i)),abs(units(p.imag)-units(hi_i)))
        d=box_squared_distance(normalize_points([p])[0],bounds)
        assert d.numerator*(1<<2148)==(dx*dx+dy*dy)*d.denominator
    return {'bit_lattice_distances':count,'bit_lattice_boxes':boxes}

def spatial_checks():
    rng=random.Random(19788401)
    cases=[]
    corners=[complex(x,y) for x in (sys.float_info.max,-sys.float_info.max,5e-324,-5e-324,0.) for y in (sys.float_info.max,-sys.float_info.max,5e-324,-5e-324,0.)]
    cases.append((corners,corners[::-1],sys.float_info.max))
    cases.append(([0.]*31,[0.]*29,0.))
    cases.append(([complex(0.,i) for i in range(-100,100)],[complex(0.,i) for i in range(-99,101)],1.))
    for _ in range(250):
        a=[complex(finite(rng),finite(rng)) for i in range(rng.randrange(1,40))]
        b=[complex(finite(rng),finite(rng)) for i in range(rng.randrange(1,45))]
        cases.append((a,b,abs(finite(rng))))
    for _ in range(250):
        a=[complex(rng.randrange(-30,31)/16,rng.randrange(-30,31)/16) for i in range(rng.randrange(1,40))]
        b=[complex(rng.randrange(-30,31)/16,rng.randrange(-30,31)/16) for i in range(rng.randrange(1,45))]
        cases.append((a,b,rng.choice([0.,.125,.75,2.,5.])))
    for a,b,t in cases:
        got=radius_graph(normalize_points(a),normalize_points(b),normalize_atol(t)**2,Budget())
        want=tuple(tuple(j for j,y in enumerate(b) if within(x,y,t)) for x in a)
        assert got==want
    return {'complete_graph_cases':len(cases)}

def integer_input():
    # Characterize binary64 integer representability using only bit lengths and low bits.
    maximum=((1<<53)-1)<<971
    def accepted(v):
        x=abs(v); bits=x.bit_length()
        return x<=maximum and (bits<=53 or x & ((1<<(bits-53))-1)==0)
    rng=random.Random(19007848); values=[0,1,-1,2**53+1,2**53+2,maximum,maximum+1,-maximum-1,2**1024,1<<100000]
    for exp in range(53,1025,7):
        values.extend([2**exp+d for d in (-3,-2,-1,0,1,2,3)])
        values.extend([rng.getrandbits(exp) for _ in range(5)])
    for v in values:
        for v in (v,-v):
            expected=accepted(v)
            for f in (lambda: normalize_points([v]), lambda: normalize_atol(abs(v))):
                try: f(); actual=True
                except ValueError: actual=False
                assert actual==expected, (v.bit_length(),v & ((1<<64)-1),expected)
    for bad in (True,False,float('inf'),float('-inf'),float('nan'),complex(float('inf'),0)):
        try: normalize_points([bad]); raise AssertionError('accepted invalid')
        except (TypeError,ValueError): pass
    return {'integers_both_signs_and_tolerance':len(values)*2}

def resource_checks():
    a=list(range(37)); b=a[::-1]
    r=compare(a,b,atol=3.)
    assert r.status=='matched'
    summaries={}
    for phase,used in r.counts:
        if not used: continue
        exact=compare(a,b,atol=3.,limits=Limits(**{'max_'+phase:used}))
        before=compare(a,b,atol=3.,limits=Limits(**{'max_'+phase:used-1}))
        assert exact.status=='matched'
        assert before.status=='resource_limited' and not before.pairs and before.hall is None
        e=before.resource
        assert e.phase==phase and e.used <= used-1 and e.used+e.requested > e.limit
        summaries[phase]=used
    for a,b in (([object()]*20001,[]),([],[object()]*20001),([0]*20001,[0]*20002)):
        r=compare(a,b,atol=0)
        assert r.status=='resource_limited' and r.actual_size==len(a) and r.expected_size==len(b)
    # Invalid bounded values are checked even when lengths differ.
    try: compare([float('nan')],[],atol=0); raise AssertionError('invalid mismatch')
    except ValueError: pass
    return {'boundary_counts':summaries,'over_limit_true_sizes':3}

def immutable_models():
    pairs=[[0,0]]; left=[0,1]; right=[0]; counts={'edges':1}
    h=HallEvidence(left,right,1)
    r=ComparisonResult('mismatch',2,2,pairs=pairs,hall=h,counts=counts)
    pairs[0][0]=1; pairs.append([1,1]); left.append(7); right.append(8); counts['edges']=0
    assert r.pairs==((0,0),) and r.hall.left_indices==(0,1) and r.hall.neighbor_indices==(0,) and r.counts==(('edges',1),)
    for obj,attr in ((r,'status'),(h,'deficiency'),(Limits(),'max_items'),(normalize_points([0])[0],'real')):
        try: setattr(obj,attr,None); raise AssertionError('mutable model')
        except (dataclasses.FrozenInstanceError,AttributeError): pass
    for obj in (r,BottleneckResult('optimal',0,0)):
        try: bool(obj); raise AssertionError('truthy result')
        except TypeError: pass
    return {'alias_checks':'pairs, Hall sides, counts','frozen_checks':4,'ambiguous_bool_rejections':2}

if __name__=='__main__':
    run('all_66067_square_graphs',exhaustive_graphs)
    run('random_rectangular_graphs',random_rectangular)
    run('extended_iterative_paths',long_paths)
    run('exact_geometry',geometry_checks)
    run('complete_spatial_graphs',spatial_checks)
    run('integer_contract',integer_input)
    run('resource_boundaries',resource_checks)
    run('immutable_models',immutable_models)
    REPORT['after']=hashes(); REPORT['stable_tested_source']=all(REPORT['before'].get(k)==REPORT['after'].get(k) for k in ('contract.py','geometry.py','models.py','spatial.py','matching.py','compare.py'))
    output=Path(__file__).with_name('core-'+str(sys.version_info.major)+str(sys.version_info.minor)+'.json')
    output.write_text(json.dumps(REPORT,indent=2)+'\n')
    print(output, 'failures',REPORT['failures'],'stable',REPORT['stable_tested_source'])
    sys.exit(bool(REPORT['failures']))
