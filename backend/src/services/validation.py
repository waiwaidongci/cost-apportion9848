import math
from datetime import date
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
def validate_material_doc(d):
 if not isinstance(d,dict) or not set(d)<= {'material','kind','doc_no','biz_date','qty','unit_cost_cents','link_no'}: raise ValueError('单据字段必须是物料/类型/单号/业务日期/数量/单价分/原领料单号')
 for key in ('material','kind','doc_no','biz_date','qty'):
  if key not in d: raise ValueError('单据缺少字段 '+key)
 if not isinstance(d['material'],str) or not 1<=len(d['material'])<=60: raise ValueError('物料名不能为空或过长')
 if d['kind'] not in ('in','out','ret'): raise ValueError('单据类型必须是入库in/领料out/退料ret')
 if not isinstance(d['doc_no'],str) or not 1<=len(d['doc_no'])<=64: raise ValueError('单号不能为空或过长')
 try: date.fromisoformat(d['biz_date'])
 except Exception: raise ValueError('业务日期必须是YYYY-MM-DD')
 number(d['qty'],'数量',minimum=1,integer=True)
 if d['kind']=='in':
  if 'unit_cost_cents' not in d: raise ValueError('入库单必须填写整数分单价')
  number(d['unit_cost_cents'],'单价分',integer=True)
  if d.get('link_no'): raise ValueError('入库单不能引用原领料单')
 elif d['kind']=='out':
  if d.get('unit_cost_cents') is not None: raise ValueError('领料单不填单价，按批次先进先出计价')
  if d.get('link_no'): raise ValueError('领料单不能引用原领料单')
 else:
  if not isinstance(d.get('link_no'),str) or not d['link_no']: raise ValueError('退料单必须引用原领料单号')
  if d.get('unit_cost_cents') is not None: raise ValueError('退料单不填单价，按原批次整数分退回')
