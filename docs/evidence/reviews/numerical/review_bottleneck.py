"""Independent assignment/certificate checks using IEEE754 lattice arithmetic."""
import copy
import decimal
from fractions import Fraction
import itertools
import json
import math
from pathlib import Path
import random
import sys
from unittest.mock import patch

import review_core as c
from bijectionlens.bottleneck import bottleneck
from bijectionlens.verify import verify_comparison, verify_bottleneck
from bijectionlens.contract import Limits
from bijectionlens.codec import to_dict

SCALE2=1<<2148

def validate_bottleneck(a,b,r):
    assert r.status=='optimal',r
    n=len(a)
    ds=[[c.distance_units(x,y) for y in b] for x in a]
    optimum=min((max((ds[i][j] for i,j in enumerate(p)),default=0) for p in itertools.permutations(range(n))),default=0)
    num,den=int(r.q_numerator),int(r.q_denominator)
    assert num*SCALE2==optimum*den,(a,b,r,optimum)
    assert math.gcd(num,den)==1
    assert len(r.pairs)==n and set(i for i,j in r.pairs)==set(range(n)) and set(j for i,j in r.pairs)==set(range(n))
    assert all(ds[i][j]<=optimum for i,j in r.pairs)
    if optimum:
        h=r.strict_hall
        actual={j for i in h.left_indices for j in range(n) if ds[i][j]<optimum}
        assert set(h.neighbor_indices)==actual and len(h.left_indices)-len(actual)==h.deficiency>0
    else: assert r.strict_hall is None
    least=r.least_finite_binary64_atol
    if least is None:
        assert c.units(sys.float_info.max)**2<optimum
    else:
        t=float.fromhex(least)
        assert t>=0 and math.isfinite(t) and t.hex()==least
        assert c.units(t)**2>=optimum
        if t>0: assert c.units(math.nextafter(t,0.))**2<optimum
        else: assert optimum==0 and least=='0x0.0p+0'
    v=verify_bottleneck(a,b,result=r)
    assert v.status=='valid',(r,v)
    return optimum

def permutation_cases():
    rng=random.Random(611385)
    cases=[([],[]),([0]*7,[0]*7),([0,3],[0,-1+2.5j]),([0],[1+1j]),([0],[5e-324+5e-324j]),
           ([-sys.float_info.max],[sys.float_info.max]),([complex(sys.float_info.max,sys.float_info.max)],[complex(-sys.float_info.max,-sys.float_info.max)]),
           ([sys.float_info.max,5e-324],[complex(sys.float_info.max,5e-324),-5e-324])]
    for _ in range(600):
        n=rng.randrange(8)
        a=[complex(rng.randrange(-32,33)/8,rng.randrange(-32,33)/8) for _ in range(n)]
        b=[complex(rng.randrange(-32,33)/8,rng.randrange(-32,33)/8) for _ in range(n)]
        cases.append((a,b))
    for _ in range(80):
        n=rng.randrange(1,5)
        a=[complex(c.finite(rng),c.finite(rng)) for _ in range(n)]
        b=[complex(c.finite(rng),c.finite(rng)) for _ in range(n)]
        cases.append((a,b))
    assignments=0
    for a,b in cases:
        r=bottleneck(a,b); validate_bottleneck(a,b,r); assignments+=math.factorial(len(a))
    return {'cases':len(cases),'enumerated_permutations':assignments,'seed':611385}

def compare_random():
    rng=random.Random(58899230); statuses={}
    for _ in range(1000):
        n=rng.randrange(9)
        a=[complex(rng.randrange(-3,4)/2,rng.randrange(-3,4)/2) for _ in range(n)]
        b=[complex(rng.randrange(-3,4)/2,rng.randrange(-3,4)/2) for _ in range(n)]
        t=rng.choice([0.,.5,1.,1.5,2.])
        graph=tuple(tuple(j for j,y in enumerate(b) if c.within(x,y,t)) for x in a)
        optimum=c.oracle_card(graph,n)
        r=c.compare(a,b,atol=t)
        assert len(r.pairs)==optimum and r.status==('matched' if optimum==n else 'mismatch')
        v=verify_comparison(a,b,atol=t,result=r)
        assert v.status=='valid',(r,v)
        statuses[r.status]=statuses.get(r.status,0)+1
    return {'cases':1000,'statuses':statuses}

def candidate_truth(a,b,t,cert):
    n=len(a); pairs=cert['pairs']; h=cert['hall']
    if len(set(i for i,j in pairs))<len(pairs) or len(set(j for i,j in pairs))<len(pairs): return False
    if not all(0<=i<n and 0<=j<n and c.within(a[i],b[j],t) for i,j in pairs): return False
    if cert['status']=='matched': return len(pairs)==n and h is None
    if len(pairs)>=n or h is None: return False
    s=h['left_indices']; ns=h['neighbor_indices']; d=h['deficiency']
    if len(set(s))!=len(s) or len(set(ns))!=len(ns) or d<=0 or len(s)-len(ns)!=d or d!=n-len(pairs): return False
    return set(ns)=={j for i in s for j in range(n) if c.within(a[i],b[j],t)}

def synthetic_comparison_certificates():
    rng=random.Random(59840083); statuses={'valid':0,'invalid':0}
    for _ in range(12000):
        n=rng.randrange(1,5); a=[rng.randrange(3) for i in range(n)]; b=[rng.randrange(3) for i in range(n)]; t=rng.choice([0,1,2])
        k=rng.randrange(n+1)
        ii=rng.sample(range(n),k); jj=rng.sample(range(n),k)
        s=[i for i in range(n) if rng.randrange(2)]; ns=[j for j in range(n) if rng.randrange(2)]
        cert={'status':rng.choice(['matched','mismatch']),'actual_size':n,'expected_size':n,'pairs':list(map(list,zip(ii,jj))),
              'hall':None if rng.randrange(5)==0 else {'left_indices':s,'neighbor_indices':ns,'deficiency':rng.randrange(n+1)}}
        want='valid' if candidate_truth(a,b,t,cert) else 'invalid'
        got=verify_comparison(a,b,atol=t,result=cert)
        assert got.status==want,(a,b,t,cert,got,want)
        statuses[want]+=1
    return {'certificates':12000,'statuses':statuses}

def synthetic_bottleneck_certificates():
    rng=random.Random(312934); statuses={'valid':0,'invalid':0}
    for _ in range(5000):
        n=rng.randrange(1,5); a=[complex(rng.randrange(3),rng.randrange(2)) for i in range(n)]; b=[complex(rng.randrange(3),rng.randrange(2)) for i in range(n)]
        q=rng.choice([0,1,2,4,5,8,9]); p=list(rng.sample(range(n),n)); s=[i for i in range(n) if rng.randrange(2)]; ns=[j for j in range(n) if rng.randrange(2)]
        least=math.sqrt(q)
        while c.units(least)**2<q*SCALE2: least=math.nextafter(least,math.inf)
        cert={'status':'optimal','actual_size':n,'expected_size':n,'pairs':[[i,j] for i,j in enumerate(p)],'q_numerator':str(q),'q_denominator':'1',
              'strict_hall':None if q==0 else {'left_indices':s,'neighbor_indices':ns,'deficiency':len(s)-len(ns)},'least_finite_binary64_atol':least.hex()}
        neighborhood={j for i in s for j in range(n) if c.distance_units(a[i],b[j])<q*SCALE2}
        want=(all(c.distance_units(a[i],b[j])<=q*SCALE2 for i,j in enumerate(p)) and
              (q==0 or len(s)>len(ns) and set(ns)==neighborhood))
        observed=verify_bottleneck(a,b,result=cert)
        expected='valid' if want else 'invalid'
        assert observed.status==expected,(a,b,cert,observed,expected)
        statuses[expected]+=1
    return {'certificates':5000,'statuses':statuses}

def exhaustive_small_real_inputs():
    # All n<=3 multisets over a three-point real alphabet, with 3 radii.
    cases=0
    for n in range(4):
        for a in itertools.product((-1.,0.,1.),repeat=n):
            for b in itertools.product((-1.,0.,1.),repeat=n):
                r=bottleneck(a,b); validate_bottleneck(a,b,r)
                for t in (0.,1.,2.):
                    result=c.compare(a,b,atol=t)
                    assert verify_comparison(a,b,atol=t,result=result).status=='valid'
                    assert (result.status=='matched')==(int(r.q_numerator)*SCALE2<=c.units(t)**2*int(r.q_denominator))
                    cases+=1
    return {'comparison_cases':cases,'bottleneck_cases':cases//3}

def bottleneck_limits():
    a=[0,1,4,7]; b=[2,5,6,8]
    r=bottleneck(a,b); assert r.status=='optimal'
    limits={}
    for phase,used in r.counts:
        if not used: continue
        exact=bottleneck(a,b,limits=Limits(**{'max_'+phase:used}))
        short=bottleneck(a,b,limits=Limits(**{'max_'+phase:used-1}))
        assert exact.status=='optimal' and short.status=='resource_limited',(phase,used,short)
        assert short.pairs==() and short.strict_hall is None and short.q_numerator is None and short.q_denominator is None and short.approximate_atol is None and short.least_finite_binary64_atol is None
        assert short.resource.used+short.resource.requested>short.resource.limit
        limits[phase]=used
    v=verify_bottleneck(a,b,result=r); used=dict(v.counts)['verify_pairs']
    assert verify_bottleneck(a,b,result=r,limits=Limits(max_verify_pairs=used)).status=='valid'
    assert verify_bottleneck(a,b,result=r,limits=Limits(max_verify_pairs=used-1)).status=='resource_limited'
    for a,b in (([object()]*20001,[]),([],[object()]*20001)):
        r=bottleneck(a,b)
        assert r.status=='resource_limited' and r.actual_size==len(a) and r.expected_size==len(b)
    return {'phase_exact_counts':limits,'verify_pairs':used}

def determinism_and_permutations():
    a=[0,.75,1.5];b=[.8,.05,1.55]
    first=None
    for left in itertools.permutations(a):
        for right in itertools.permutations(b):
            r=bottleneck(left,right); validate_bottleneck(left,right,r)
            q=(r.q_numerator,r.q_denominator)
            if first is None:first=q
            assert q==first
    serials=[json.dumps(to_dict(bottleneck(a,b)),sort_keys=True) for _ in range(10)]
    assert len(set(serials))==1
    return {'input_permutation_pairs':36,'byte_equivalent_serializations':10}

def ambient_decimal():
    reference=to_dict(bottleneck([0],[1+1j]))
    with decimal.localcontext() as context:
        context.traps[decimal.Inexact]=True; context.Emax=1; context.Emin=-1; context.rounding=decimal.ROUND_FLOOR
        assert to_dict(bottleneck([0],[1+1j]))==reference
    old=decimal.DefaultContext.copy()
    try:
        decimal.DefaultContext.traps[decimal.Inexact]=True
        decimal.DefaultContext.Emax=1; decimal.DefaultContext.Emin=-1; decimal.DefaultContext.rounding=decimal.ROUND_FLOOR
        assert to_dict(bottleneck([0],[1+1j]))==reference
    finally:
        for attr in ('prec','Emax','Emin','rounding','capitals','clamp'):setattr(decimal.DefaultContext,attr,getattr(old,attr))
        decimal.DefaultContext.traps=old.traps.copy(); decimal.DefaultContext.flags=old.flags.copy()
    return {'current_context':'isolated','DefaultContext':'isolated'}

if __name__=='__main__':
    c.run('permutation_bottleneck',permutation_cases)
    c.run('random_comparison',compare_random)
    c.run('synthetic_comparison_certificates',synthetic_comparison_certificates)
    c.run('synthetic_bottleneck_certificates',synthetic_bottleneck_certificates)
    c.run('exhaustive_small_real_inputs',exhaustive_small_real_inputs)
    c.run('bottleneck_limits',bottleneck_limits)
    c.run('determinism_and_permutations',determinism_and_permutations)
    c.run('ambient_decimal',ambient_decimal)
    c.REPORT['after']=c.hashes(); c.REPORT['stable_tested_source']=all(c.REPORT['before'].get(k)==c.REPORT['after'].get(k) for k in ('contract.py','geometry.py','models.py','spatial.py','matching.py','compare.py','bottleneck.py','verify.py','codec.py','__init__.py'))
    output=Path(__file__).with_name('bottleneck-'+str(sys.version_info.major)+str(sys.version_info.minor)+'.json')
    output.write_text(json.dumps(c.REPORT,indent=2)+'\n')
    print(output,'failures',c.REPORT['failures'],'stable',c.REPORT['stable_tested_source'])
    sys.exit(bool(c.REPORT['failures']))
