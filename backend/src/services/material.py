"""材料批次台账编排：单据登记/冲销、增量重算、一次性切换、全量核对。

一致性口径：
- 单据与重算结果在同一事务提交，算完再一次性切换批次/明细/汇总；
- 每个物料一把事务级咨询锁+账户行锁，并发补录或领退串行，旧结果不会覆盖新账；
- 重算按指纹链幂等：单据未变时空转，崩溃恢复后重跑不会重复归集；
- 重算失败不切换，账户进入错单状态并指出首笔错单，已生效领退金额保持不变。
"""
import time
from fastapi import HTTPException
from sqlalchemy import text
from src.models.material import MaterialDoc,MaterialBatch,MaterialLine,MaterialCheckpoint,MaterialAccount
from src.services import ledger
from src.services.audit import log
from src.services.validation import validate_material_doc

def _doc(r):return {'id':r.id,'kind':r.kind,'doc_no':r.doc_no,'biz_date':r.biz_date,'qty':r.qty,'unit_cost_cents':r.unit_cost_cents,'link_no':r.link_no}
def _line(r):return {'doc_id':r.doc_id,'doc_index':r.doc_index,'line_seq':r.line_seq,'direction':r.direction,'in_doc_id':r.in_doc_id,'issue_doc_id':r.issue_doc_id,'issue_line_seq':r.issue_line_seq,'qty':r.qty,'unit_cost_cents':r.unit_cost_cents,'amount_cents':r.amount_cents}

def _lock(db,material):
 try:db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:m))'),{'m':material})
 except Exception:pass  # 非Postgres方言（本地sqlite冒烟）退化为行锁串行

def _account_for_update(db,material):
 try:return db.query(MaterialAccount).filter_by(material=material).with_for_update().first()
 except Exception:return db.query(MaterialAccount).filter_by(material=material).first()

def recalc(db,material):
 """从该物料最早变动处增量重算；全部写操作随调用方事务一次提交。"""
 _lock(db,material)
 account=_account_for_update(db,material)
 if not account:
  account=MaterialAccount(material=material,version=0,status='ok',error='',processed=[],totals={},recalc={},updated=0);db.add(account);db.flush()
 docs=ledger.order_docs([_doc(x) for x in db.query(MaterialDoc).filter_by(material=material).all()])
 prints=ledger.fingerprints(docs)
 if account.status=='ok' and account.processed==prints:return account,{'noop':True,'replayed':0}
 d=ledger.divergence(account.processed or [],prints)
 cp=db.query(MaterialCheckpoint).filter(MaterialCheckpoint.material==material,MaterialCheckpoint.doc_index<d).order_by(MaterialCheckpoint.doc_index.desc()).first()
 start=cp.doc_index+1 if cp else 0
 batches=[dict(b) for b in (cp.batches if cp else [])]
 issue_lines={};returned={}
 kept=db.query(MaterialLine).filter(MaterialLine.material==material,MaterialLine.doc_index<start).order_by(MaterialLine.doc_index,MaterialLine.line_seq).all()
 for r in kept:
  l=_line(r)
  if l['direction']=='issue':issue_lines.setdefault(l['doc_id'],[]).append(l)
  else:returned[(l['issue_doc_id'],l['issue_line_seq'])]=returned.get((l['issue_doc_id'],l['issue_line_seq']),0)+l['qty']
 try:
  new_lines,snaps=ledger.replay(docs,start,batches,issue_lines,returned)
 except ledger.LedgerError as exc:
  account.status='error';account.error=str(exc);account.recalc={'from_index':start,'divergence':d,'replayed':0,'at':time.time()};account.updated=time.time()
  return account,{'error':str(exc),'replayed':0}
 db.query(MaterialLine).filter(MaterialLine.material==material,MaterialLine.doc_index>=start).delete(synchronize_session=False)
 for l in new_lines:db.add(MaterialLine(material=material,**l))
 db.query(MaterialBatch).filter(MaterialBatch.material==material).delete(synchronize_session=False)
 for b in batches:db.add(MaterialBatch(material=material,**b))
 db.query(MaterialCheckpoint).filter(MaterialCheckpoint.material==material,MaterialCheckpoint.doc_index>=start).delete(synchronize_session=False)
 for i,snap in snaps:db.add(MaterialCheckpoint(material=material,doc_index=i,doc_id=docs[i]['id'],batches=snap))
 account.totals=ledger.summarize(docs,batches,[_line(r) for r in kept]+new_lines)
 account.processed=prints;account.status='ok';account.error='';account.version=(account.version or 0)+1
 account.recalc={'from_index':start,'divergence':d,'replayed':len(docs)-start,'at':time.time()};account.updated=time.time()
 return account,{'replayed':len(docs)-start}

def post_doc(db,user,data):
 validate_material_doc(data)
 if db.query(MaterialDoc).filter_by(doc_no=data['doc_no']).first():raise HTTPException(409,'单号已存在；重复提交不会产生新单')
 if data['kind']==ledger.RET:
  target=db.query(MaterialDoc).filter_by(doc_no=data['link_no']).first()
  if not target or target.kind!=ledger.OUT or target.material!=data['material']:raise HTTPException(422,'原领料单不存在，或不是同物料的领料单')
  if (data['biz_date'],data['doc_no'])<=(target.biz_date,target.doc_no):raise HTTPException(422,'退料单的业务日期与单号必须晚于原领料单')
 doc=MaterialDoc(material=data['material'],kind=data['kind'],doc_no=data['doc_no'],biz_date=data['biz_date'],qty=data['qty'],unit_cost_cents=data.get('unit_cost_cents'),link_no=data.get('link_no'),actor=user.email,created=time.time())
 db.add(doc);db.flush()
 account,info=recalc(db,data['material'])
 log(db,user.email,'material.post',f"{data['doc_no']} {data['kind']} {data['material']}")
 db.commit();return account,info

def delete_doc(db,user,doc_id):
 doc=db.get(MaterialDoc,doc_id)
 if not doc:raise HTTPException(404,'单据不存在')
 material=doc.material;no=doc.doc_no
 db.delete(doc);db.flush()
 account,info=recalc(db,material)
 log(db,user.email,'material.delete',f'{no} {material}')
 db.commit();return account,info

def account_view(a):
 return {'material':a.material,'version':a.version,'status':a.status,'error':a.error or '','totals':a.totals or {},'recalc':a.recalc or {},'updated':a.updated or 0}

def list_accounts(db):return [account_view(a) for a in db.query(MaterialAccount).order_by(MaterialAccount.material).all()]

def detail(db,material):
 account=db.get(MaterialAccount,material)
 sums={}
 for r in db.query(MaterialLine).filter(MaterialLine.material==material).all():sums[r.doc_id]=sums.get(r.doc_id,0)+r.amount_cents
 rows=sorted(db.query(MaterialDoc).filter_by(material=material).all(),key=lambda x:ledger.doc_key(_doc(x)))
 docs=[{'id':x.id,'material':x.material,'kind':x.kind,'doc_no':x.doc_no,'biz_date':x.biz_date,'qty':x.qty,'unit_cost_cents':x.unit_cost_cents,'link_no':x.link_no,'actor':x.actor,'created':x.created,'allocated_cents':(x.qty*x.unit_cost_cents if x.kind==ledger.IN else sums.get(x.id,0))} for x in rows]
 batches=[{'in_doc_id':b.in_doc_id,'doc_no':b.doc_no,'biz_date':b.biz_date,'unit_cost_cents':b.unit_cost_cents,'qty':b.qty,'amount_cents':b.qty*b.unit_cost_cents} for b in db.query(MaterialBatch).filter_by(material=material).order_by(MaterialBatch.id).all()]
 return {'account':account_view(account) if account else None,'docs':docs,'batches':batches}

def doc_lines(db,doc_id):
 doc=db.get(MaterialDoc,doc_id)
 if not doc:raise HTTPException(404,'单据不存在')
 nos={x.id:x.doc_no for x in db.query(MaterialDoc).filter_by(material=doc.material).all()}
 rows=db.query(MaterialLine).filter_by(doc_id=doc_id).order_by(MaterialLine.line_seq).all()
 return [{'id':r.id,'doc_id':r.doc_id,'doc_index':r.doc_index,'line_seq':r.line_seq,'direction':r.direction,'in_doc_id':r.in_doc_id,'batch_doc_no':nos.get(r.in_doc_id,''),'qty':r.qty,'unit_cost_cents':r.unit_cost_cents,'amount_cents':r.amount_cents,'issue_doc_id':r.issue_doc_id,'issue_line_seq':r.issue_line_seq} for r in rows]

def verify(db,user,material):
 """全量重算并与已生效台账核对（只读核对，不切换任何账）。"""
 docs=ledger.order_docs([_doc(x) for x in db.query(MaterialDoc).filter_by(material=material).all()])
 batches=[];issue_lines={};returned={};diffs=[]
 try:
  lines,_=ledger.replay(docs,0,batches,issue_lines,returned)
  full={'batches':batches,'lines':lines,'totals':ledger.summarize(docs,batches,lines)}
 except ledger.LedgerError as exc:full={'error':str(exc)}
 account=db.get(MaterialAccount,material)
 stored_lines=db.query(MaterialLine).filter_by(material=material).all()
 stored_batches=db.query(MaterialBatch).filter_by(material=material).all()
 if 'error' in full:
  if not account or account.status!='error' or account.error!=full['error']:diffs.append('全量重算的首笔错单与台账状态不一致：'+full['error'])
 elif not account or account.status!='ok':diffs.append('全量重算成功但台账处于错单状态')
 else:
  bk=lambda rows:sorted((b['in_doc_id'],b['qty'],b['unit_cost_cents']) for b in rows)
  if bk([_line_batch(b) for b in stored_batches])!=bk(full['batches']):diffs.append('批次结存不一致')
  lk=lambda rows:sorted((l['doc_id'],l['line_seq'],l['direction'],l['in_doc_id'],l['qty'],l['amount_cents']) for l in rows)
  if lk([_line(r) for r in stored_lines])!=lk(full['lines']):diffs.append('领退明细不一致')
  if account.totals!=full['totals']:diffs.append('汇总不一致')
 result={'material':material,'match':not diffs,'differences':diffs[:20],'checked':{'docs':len(docs),'lines':len(stored_lines),'batches':len(stored_batches)},'account_status':account.status if account else 'missing','account_error':account.error if account else ''}
 log(db,user.email,'material.verify',f"{material} {'一致' if not diffs else '不一致'}")
 db.commit();return result

def _line_batch(b):return {'in_doc_id':b.in_doc_id,'qty':b.qty,'unit_cost_cents':b.unit_cost_cents}

def reconcile_all(db,actor='system'):
 """崩溃恢复入口：逐物料按指纹链核对，漂移才重算；幂等，不重复归集。"""
 names={r[0] for r in db.query(MaterialDoc.material).distinct()}|{a.material for a in db.query(MaterialAccount).all()}
 done=[]
 for name in sorted(names):
  _account,info=recalc(db,name)
  if not info.get('noop'):done.append(name)
 if done:log(db,actor,'material.reconcile','、'.join(done))
 db.commit();return done
