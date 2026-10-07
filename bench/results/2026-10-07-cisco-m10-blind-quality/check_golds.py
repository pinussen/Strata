"""Independent arithmetic/OS checks of reference answers, with tiny local temp files."""
from fractions import Fraction
import ipaddress
import itertools
import json
import os
from pathlib import Path
import tempfile

out={}
with tempfile.TemporaryDirectory() as d:
    a,b=Path(d)/'a',Path(d)/'b'
    a.write_bytes(b'test fixture');os.link(a,b)
    with a.open('rb') as f:
        before=os.fstat(f.fileno()).st_nlink
        a.unlink();after_one=os.fstat(f.fileno()).st_nlink
        b.unlink();after_two=os.fstat(f.fileno()).st_nlink
        readable=f.read().decode()
    out['05']=dict(link_counts=[before,after_one,after_two],readable_after_unlink=readable)
    assert [before,after_one,after_two]==[2,1,0] and readable=='test fixture'
out['09']=dict(new_seconds=60/4+25+15+5,speedup=100/60,percent_reduction=40,
               minimum_seconds=25+15+5,maximum_speedup=100/45)
out['10']=dict(lambda_per_second=240/60,system_seconds=18/4,queue_seconds=18/4-.6,
               active_jobs=4*.6,utilization=4*.6/4)
net=ipaddress.ip_network('10.42.16.0/20')
out['11']=dict(mask=str(net.netmask),broadcast=str(net.broadcast_address),first=str(net[1]),
               last=str(net[-2]),usable=net.num_addresses-2,
               membership={a:ipaddress.ip_address(a) in net for a in ['10.42.31.254','10.42.32.1']})
out['12']=dict(last_A=100+20,last_B=100-30,serial=100+20-30)
# Exhaust all integer start times 0..8. Jobs are integral and preemption-free.
dur=[3,2,4,2,1];edges=[(0,2),(0,3),(1,3),(2,4),(3,4)];best=99;example=None
for starts in itertools.product(range(9),repeat=5):
    ends=[s+d for s,d in zip(starts,dur)]
    if max(ends)>=best or any(ends[u]>starts[v] for u,v in edges):continue
    if any(sum(s<=t<e for s,e in zip(starts,ends))>2 for t in range(max(ends))):continue
    best=max(ends);example=list(zip('ABCDE',starts,ends))
assert best==8
out['13']=dict(optimum=best,schedule=example,critical_path=3+4+1)
out['14']=dict(marked_fraction=str(Fraction(90,585)),marked_percent=100*90/585,
               unmarked_fraction=str(Fraction(10,9415)),unmarked_percent=100*10/9415)
physical,reserved=23,0;ledger=[]
for day,dp,dr in [('mån',0,7),('tis',5,0),('ons',-4,-4),('tor',0,-2),('fre',-6,0)]:
    physical+=dp;reserved+=dr;ledger.append([day,physical,reserved,physical-reserved])
out['15']=ledger
out['16']={g:sum([g=='Bo',g!='Bo',g!='Ada']) for g in ['Ada','Bo','Cia']}
out['26']=dict(R1=1250,R2=-150,R6=300,total=1250-150+300)
out['28']=dict(error_percent=9/600*100,enough_calls=600>=500,over_threshold=9/600>.02)
possibilities=[]
for both in range(26):
    x_only,y_only=19-both,21-both;neither=25-both-x_only-y_only
    if min(both,x_only,y_only,neither)>=0:
        possibilities.append(dict(both=both,x_only=x_only,y_only=y_only,ties=both+neither))
out['30']=possibilities
x=float(2**53);out['31']=[x+1==x,int(x)+1==int(x)]
out['32']=dict(A_total=(81+2)/(90+10),B_total=(19+24)/(20+80),
              A_easy=81/90,B_easy=19/20,A_hard=2/10,B_hard=24/80)
Path(__file__).with_name('gold-verification.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
print('Reference arithmetic, scheduling enumeration, subnet and local unlink checks passed.')
