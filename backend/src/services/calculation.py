from decimal import Decimal,ROUND_FLOOR
from collections import defaultdict
from src.services.validation import validate_source,validate_policy
def allocate(cents,weights):
 if isinstance(cents,bool) or not isinstance(cents,int) or cents<0: raise ValueError('金额必须为非负整数分')
 ws={k:Decimal(str(v)) for k,v in weights.items()}
 if not ws or any(v<0 for v in ws.values()) or sum(ws.values())<=0: raise ValueError('权重合计必须大于0且非负')
 total=sum(ws.values());raw={k:Decimal(cents)*w/total for k,w in ws.items()};base={k:int(v.to_integral_value(rounding=ROUND_FLOOR)) for k,v in raw.items()}
 order=sorted(ws,key=lambda k:(-(raw[k]-base[k]),k))
 for k in order[:cents-sum(base.values())]:base[k]+=1
 assert sum(base.values())==cents
 return base
def calculate(sources,policy):
 validate_policy(policy);pivot=defaultdict(int);source_total=0;public=0;trace=[]
 for s in sources:
  validate_source(s);source_total+=s['amount_cents']
  pieces=allocate(s['amount_cents'],policy['weights']) if s['department']=='公共' else {s['department']:s['amount_cents']}
  if s['department']=='公共':public+=s['amount_cents']
  for dept,v in pieces.items():pivot[(s['period'],dept,s['category'])]+=v
  trace.append({'来源序号':len(trace)+1,'期间':s['period'],'来源部门':s['department'],'费用类别':s['category'],'原始金额分':s['amount_cents'],'分配明细':pieces,'分配合计分':sum(pieces.values())})
 rows=[{'期间':p,'部门':d,'费用类别':c,'分摊金额分':v} for (p,d,c),v in sorted(pivot.items())]
 total=sum(r['分摊金额分'] for r in rows)
 return {'summary':{'来源金额分':source_total,'分摊金额分':total,'公共成本分':public,'守恒差额分':total-source_total},'rows':rows,'trace':trace,'method':'每笔公共费用按工时权重计算精确份额，向下取整后按小数余数降序、部门名升序分配剩余分。部门直归费用不分摊；透视期间×部门×费用类别。','warnings':[]}
