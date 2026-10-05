"""Independent regression/boundary review; production files remain untouched."""
import copy
import importlib
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch
import review_core as c
from bijectionlens.bottleneck import bottleneck
from bijectionlens.verify import verify_comparison,verify_bottleneck
from bijectionlens.models import ComparisonResult,BottleneckResult,HallEvidence,ResourceEvidence
from bijectionlens.contract import Limits
from bijectionlens.codec import to_dict

v=importlib.import_module('bijectionlens.verify')

def cb(**kwargs):
    cert={'status':'matched','actual_size':1,'expected_size':1,'pairs':[[0,0]]}
    cert.update(kwargs); return cert

def bb(**kwargs):
    cert={'status':'optimal','actual_size':1,'expected_size':1,'pairs':[[0,0]],'q_numerator':'0','q_denominator':'1','least_finite_binary64_atol':'0x0.0p+0'}
    cert.update(kwargs); return cert

def validators_before_arithmetic():
    cases=[(cb(pairs=[[0,0]]*20001),'resource_limited'),(cb(pairs=[[1<<64,0]]),'resource_limited'),
           (cb(pairs=[[0,0,0]]),'invalid'),(cb(pairs=[[0,2]]),'invalid'),(cb(pairs=[[0,0],[0,0]]),'invalid'),
           (cb(hall={'left_indices':[0]*20001,'neighbor_indices':[],'deficiency':1}),'resource_limited'),
           (cb(hall={'left_indices':[1],'neighbor_indices':[],'deficiency':1}),'invalid'),
           (cb(counts=[['matching_scans',20_000_001]]),'invalid'),(cb(counts=[['verify_pairs',1<<64]]),'resource_limited')]
    with patch.object(v,'squared_distance',side_effect=AssertionError('premature distance')):
        for cert,want in cases:
            got=verify_comparison([0],[0],atol=0,result=cert)
            assert got.status==want,(cert,got,want)
    rationals=[(bb(q_numerator='1'*2501),'resource_limited'),(bb(q_denominator='1'*2501),'resource_limited'),
               (bb(q_numerator=str(1<<8192)),'resource_limited'),(bb(q_denominator=str(1<<8192)),'resource_limited'),
               (bb(q_numerator='-1'),'invalid'),(bb(q_denominator='0'),'invalid'),(bb(q_numerator='01'),'invalid'),
               (bb(q_numerator='١'),'invalid')]
    with patch.object(v.math,'gcd',side_effect=AssertionError('premature gcd')):
        for cert,want in rationals:
            got=verify_bottleneck([0],[0],result=cert)
            assert got.status==want,(got,want)
    for cert in (bb(q_numerator='0',q_denominator='2'),bb(q_numerator='1',q_denominator='2')):
        assert verify_bottleneck([0],[0],result=cert).status=='invalid'
    return {'comparison_prearithmetic_cases':len(cases),'rational_prearithmetic_cases':len(rationals),'nonreduced_or_wrong_q':2}

def shapes_before_normalization():
    for verifier,cert in ((lambda a,b,r:verify_comparison(a,b,atol=0,result=r),cb()),(lambda a,b,r:verify_bottleneck(a,b,result=r),bb())):
        for a,b in (([object()],[0]*20001),([0]*20001,[object()])):
            assert verifier(a,b,cert).status=='resource_limited'
    return {'both_length_prechecks':4}

def hostile_callbacks():
    class Meta(type):
        def __eq__(cls,other):raise AssertionError('metaclass equality invoked')
    class Hostile(metaclass=Meta):
        def __iter__(self):raise AssertionError('iteration invoked')
        def __float__(self):raise AssertionError('float invoked')
        def __getattribute__(self,key):raise AssertionError('attribute invoked')
    x=Hostile(); calls=0
    for f in (lambda:c.normalize_points(x),lambda:c.compare(x,[0],atol=0),lambda:bottleneck([0],x),lambda:c.normalize_atol(x),
              lambda:ComparisonResult('matched',1,1,pairs=x),lambda:ComparisonResult('matched',1,1,pairs=[x]),lambda:HallEvidence(x,[],1)):
        try:f();raise AssertionError('accepted custom')
        except TypeError: calls+=1
    for cert in (x,cb(pairs=x),cb(pairs=[x]),cb(counts=x),cb(hall=x),cb(resource=x)):
        assert verify_comparison([0],[0],atol=0,result=cert).status=='invalid';calls+=1
    for model,cert in ((ComparisonResult,None),(BottleneckResult,None),(HallEvidence,cb()),(ResourceEvidence,cb())):
        forged=object.__new__(model)
        if cert is None:
            got=verify_comparison([],[],atol=0,result=forged) if model is ComparisonResult else verify_bottleneck([],[],result=forged)
        else:
            cert['hall' if model is HallEvidence else 'resource']=forged
            got=verify_comparison([0],[0],atol=0,result=cert)
        assert got.status=='invalid';calls+=1
    return {'no_callback_or_uncaught_exception_cases':calls}

def omission_proofs():
    wrong={'status':'mismatch','actual_size':3,'expected_size':3,'pairs':[[0,0],[2,2]],'hall':{'left_indices':[0,1],'neighbor_indices':[0],'deficiency':1}}
    # True full neighborhood is {0,1}, so listed shortage is false.
    assert verify_comparison([0,0,3],[0,0,3],atol=.1,result=wrong).status=='invalid'
    r=to_dict(bottleneck([0,0,3],[0,3,3]))
    assert verify_bottleneck([0,0,3],[0,3,3],result=r).status=='valid'
    # A feasible radius enlarged beyond optimum cannot acquire a strict proof.
    r['q_numerator']='16';r['q_denominator']='1';r['least_finite_binary64_atol']=(4.).hex()
    assert verify_bottleneck([0,0,3],[0,3,3],result=r).status=='invalid'
    return {'omitted_complete_neighbor':'invalid','feasible_nonoptimum':'invalid'}

def low_integer_string_cap():
    pairs=[([0],[5e-324]),([sys.float_info.max],[5e-324]),([complex(sys.float_info.max,5e-324)],[complex(-sys.float_info.max,-5e-324)])]
    originals=[bottleneck(a,b) for a,b in pairs]
    previous=sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(640)
        for (a,b),r in zip(pairs,originals):
            assert verify_bottleneck(a,b,result=r).status=='valid'
            assert to_dict(bottleneck(a,b))==to_dict(r)
    finally:sys.set_int_max_str_digits(previous)
    return {'setting':640,'extreme_certificates':3,'global_setting_restored':True}

def full_pair_cap():
    maximum=Limits().max_bottleneck_pairs
    n=math.isqrt(maximum)
    r=bottleneck([0]*n,[0]*n)
    assert r.status=='optimal' and dict(r.counts)['bottleneck_pairs']==n*n
    over=bottleneck([0]*(n+1),[0]*(n+1))
    assert over.status=='resource_limited' and over.resource.phase=='bottleneck_pairs'
    assert over.resource.used==maximum and over.resource.requested==1
    assert over.q_numerator is None and over.pairs==() and over.strict_hall is None
    return {'hard_pair_cap':maximum,'largest_square_admitted':n,'first_over_square':n+1}

if __name__=='__main__':
    c.run('prearithmetic_shape_and_rational_bounds',validators_before_arithmetic)
    c.run('both_input_length_prechecks',shapes_before_normalization)
    c.run('strict_types_and_missing_slots',hostile_callbacks)
    c.run('all_neighbor_omission_and_optimality',omission_proofs)
    c.run('low_integer_string_cap',low_integer_string_cap)
    c.run('hard_bottleneck_pair_cap',full_pair_cap)
    c.REPORT['after']=c.hashes();c.REPORT['stable_tested_source']=all(c.REPORT['before'].get(k)==c.REPORT['after'].get(k) for k in ('contract.py','geometry.py','models.py','spatial.py','matching.py','compare.py','bottleneck.py','verify.py','codec.py','__init__.py'))
    output=Path(__file__).with_name('adversarial-'+str(sys.version_info.major)+str(sys.version_info.minor)+'.json')
    output.write_text(json.dumps(c.REPORT,indent=2)+'\n')
    print(output,'failures',c.REPORT['failures'],'stable',c.REPORT['stable_tested_source'])
    sys.exit(bool(c.REPORT['failures']))
