"""材料批次台账纯函数引擎（不依赖数据库，可单测）。

口径：
- 同物料单据按（业务日期, 单号, 主键）排序重放；
- 入库产生批次；领料从最早有余量的批次扣减，金额=数量×批次整数分单价；
- 退料按原领料扣减的反序退回原批次，整数分成本与原扣减一致；
- 任一单据导致负库存、超退或引用失效，抛出指明首笔错单的 LedgerError；
- 增量重算：按指纹链定位最早分歧点，从最近的批次检查点恢复后只重放后缀。
"""
import hashlib,json

IN,OUT,RET='in','out','ret'
CHECKPOINT_EVERY=25

def doc_key(doc):return (doc['biz_date'],doc['doc_no'],doc['id'])
def order_docs(docs):return sorted(docs,key=doc_key)

def fingerprint(doc):
 payload={k:doc.get(k) for k in ('id','kind','doc_no','biz_date','qty','unit_cost_cents','link_no')}
 return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]

def fingerprints(docs):return [fingerprint(d) for d in docs]

def divergence(old,new):
 """已生效指纹链与当前单据指纹链的首个不一致位置；old为new前缀时返回len(old)（纯追加）。"""
 n=min(len(old),len(new))
 for i in range(n):
  if old[i]!=new[i]:return i
 return n

class LedgerError(Exception):
 def __init__(self,index,doc,reason,detail):
  self.index=index;self.doc_no=doc['doc_no'];self.reason=reason;self.detail=detail
  super().__init__(f"首笔错单 {doc['doc_no']}（{doc['biz_date']}）：{reason}。{detail}")

def replay(docs,start,batches,issue_lines,returned,every=CHECKPOINT_EVERY):
 """从start重放到末尾；就地修改 batches/issue_lines/returned。
 batches: [{'in_doc_id','doc_no','biz_date','unit_cost_cents','qty'}] 起始批次状态；
 issue_lines: {领料单id: [扣减行]}；returned: {(领料单id,行号): 已退数量}。
 返回（新明细行, 检查点[(doc_index,批次快照)]）；出错抛 LedgerError。"""
 by_no={d['doc_no']:d for d in docs}
 by_batch={b['in_doc_id']:b for b in batches}
 lines=[];snaps=[]
 for i in range(start,len(docs)):
  doc=docs[i];kind=doc['kind']
  if kind==IN:
   batch={'in_doc_id':doc['id'],'doc_no':doc['doc_no'],'biz_date':doc['biz_date'],'unit_cost_cents':doc['unit_cost_cents'],'qty':doc['qty']}
   batches.append(batch);by_batch[batch['in_doc_id']]=batch
  elif kind==OUT:
   available=sum(b['qty'] for b in batches)
   if available<doc['qty']:raise LedgerError(i,doc,'负库存',f"领料{doc['qty']}个，当前结存仅{available}个")
   need=doc['qty'];seq=0
   for b in batches:
    if need==0:break
    if b['qty']<=0:continue
    take=min(need,b['qty']);b['qty']-=take;need-=take
    line={'doc_id':doc['id'],'doc_index':i,'line_seq':seq,'direction':'issue','in_doc_id':b['in_doc_id'],'issue_doc_id':doc['id'],'issue_line_seq':seq,'qty':take,'unit_cost_cents':b['unit_cost_cents'],'amount_cents':take*b['unit_cost_cents']}
    lines.append(line);issue_lines.setdefault(doc['id'],[]).append(line);seq+=1
  else:
   target=by_no.get(doc.get('link_no'))
   if not target or target['kind']!=OUT:raise LedgerError(i,doc,'退料引用无效',f"原领料单{doc.get('link_no')}不存在或不是领料单")
   if doc_key(target)>=doc_key(doc):raise LedgerError(i,doc,'退料引用无效',f"原领料单{target['doc_no']}不早于本退料单")
   ilines=issue_lines.get(target['id'])
   if ilines is None:raise LedgerError(i,doc,'退料引用无效',f"原领料单{target['doc_no']}尚未生效")
   done=sum(v for (iid,_s),v in returned.items() if iid==target['id'])
   if done+doc['qty']>target['qty']:raise LedgerError(i,doc,'超退',f"累计退料{done+doc['qty']}个，超过原领料{target['qty']}个")
   need=doc['qty'];seq=0
   for il in reversed(ilines):
    if need==0:break
    key=(target['id'],il['line_seq']);avail=il['qty']-returned.get(key,0)
    if avail<=0:continue
    take=min(need,avail);returned[key]=returned.get(key,0)+take;need-=take
    by_batch[il['in_doc_id']]['qty']+=take
    lines.append({'doc_id':doc['id'],'doc_index':i,'line_seq':seq,'direction':'return','in_doc_id':il['in_doc_id'],'issue_doc_id':target['id'],'issue_line_seq':il['line_seq'],'qty':take,'unit_cost_cents':il['unit_cost_cents'],'amount_cents':take*il['unit_cost_cents']})
    seq+=1
  if (i+1)%every==0:snaps.append((i,[dict(b) for b in batches]))
 return lines,snaps

def summarize(docs,batches,lines):
 """台账汇总；守恒：结存=入库-领用+退回（数量与整数分金额分别成立）。"""
 def total(direction,field):return sum(l[field] for l in lines if l['direction']==direction)
 inbound_qty=sum(d['qty'] for d in docs if d['kind']==IN)
 inbound_cents=sum(d['qty']*d['unit_cost_cents'] for d in docs if d['kind']==IN)
 return {'doc_count':len(docs),'inbound_qty':inbound_qty,'inbound_cents':inbound_cents,'issued_qty':total('issue','qty'),'issued_cents':total('issue','amount_cents'),'returned_qty':total('return','qty'),'returned_cents':total('return','amount_cents'),'on_hand_qty':sum(b['qty'] for b in batches),'on_hand_cents':sum(b['qty']*b['unit_cost_cents'] for b in batches)}
