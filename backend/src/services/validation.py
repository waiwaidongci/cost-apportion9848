import math
from src.config.settings import CONFIG
def number(value,name,minimum=0,integer=False):
 if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<minimum or (integer and int(value)!=value): raise ValueError(name+'数值不合法')
 return value
def validate_source(d):
 if not isinstance(d,dict) or set(d)!=set(CONFIG['fields']): raise ValueError('底稿字段必须与业务字段一致')
 for key in ('period','department'):
  if not isinstance(d[key],str) or not 1<=len(d[key])<=100: raise ValueError(key+'不能为空或过长')
 number(d['amount_cents'],'金额分',integer=True)
 if not isinstance(d['category'],str) or not d['category'].strip(): raise ValueError('费用类别不能为空')
def validate_policy(d):
 if not isinstance(d,dict) or not isinstance(d.get('version'),str) or not 2<=len(d['version'])<=120: raise ValueError('口径版本名不合法')
 weights=d.get('weights')
 if not isinstance(weights,dict) or not weights or len(weights)>20: raise ValueError('工时权重需为非空对象且不超过20部门')
 for k,v in weights.items():
  if not isinstance(k,str) or not k or k=='公共': raise ValueError('分摊部门名不合法')
  number(v,'工时权重')
 if sum(weights.values())<=0: raise ValueError('工时权重合计必须大于0')
