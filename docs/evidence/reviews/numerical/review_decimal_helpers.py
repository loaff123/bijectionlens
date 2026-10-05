"""Bounded decimal helpers compared to independent builtin conversions."""
import json
from pathlib import Path
import random
import sys
import review_core as c
from bijectionlens.contract import parse_certificate_decimal, format_certificate_decimal, ResourceLimit

def check_helpers():
    rng=random.Random(67211801)
    values=[0,1,10**9-1,10**9,10**9+1,(1<<8192)-1]
    values.extend(rng.getrandbits(rng.randrange(8193)) for _ in range(300))
    expected=[str(value) for value in values]
    previous=sys.get_int_max_str_digits()
    try:
        for cap in (640,0,4300):
            sys.set_int_max_str_digits(cap)
            for value,spelling in zip(values,expected):
                assert format_certificate_decimal(value)==spelling
                assert parse_certificate_decimal(spelling)==value
                assert sys.get_int_max_str_digits()==cap
        for value in (1<<8192,1<<100000):
            try:format_certificate_decimal(value);raise AssertionError('out of bound accepted')
            except ResourceLimit:pass
        for text in ('9'*2501,'9'*2500):
            try:parse_certificate_decimal(text);raise AssertionError('out of bound accepted')
            except ResourceLimit:pass
        for text in ('','00','01','+1','-1','1.0',' 1','١','１'):
            try:parse_certificate_decimal(text);raise AssertionError('noncanonical accepted')
            except ValueError:pass
        for value in (True,False,1.0,object()):
            for fn in (parse_certificate_decimal,format_certificate_decimal):
                try:fn(value);raise AssertionError('nonbuiltin accepted')
                except TypeError:pass
    finally:sys.set_int_max_str_digits(previous)
    return {'random_plus_boundary_integers':len(values),'ambient_caps':[640,0,4300],'conversions':len(values)*3*2,'max_bits':8192,'setting_unchanged_by_helpers':True}

c.run('bounded_decimal_helper_oracle',check_helpers)
c.REPORT['after']=c.hashes();c.REPORT['stable_tested_source']=c.REPORT['before']['contract.py']==c.REPORT['after']['contract.py']
output=Path(__file__).with_name('decimal-'+str(sys.version_info.major)+str(sys.version_info.minor)+'.json')
output.write_text(json.dumps(c.REPORT,indent=2)+'\n')
print(output,'failures',c.REPORT['failures'],'stable',c.REPORT['stable_tested_source'])
sys.exit(bool(c.REPORT['failures']))
