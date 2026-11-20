"""材料批次台账引擎测试：FIFO、反序退料、整数分、首笔错单、增量=全量、幂等。
运行：cd backend && python3 -m unittest discover -s tests -v
"""
import random,unittest
from src.services import ledger
from src.services.ledger import LedgerError,replay,order_docs,fingerprints,divergence,summarize

def doc(id,kind,no,date,qty,unit=None,link=None):
 return {'id':id,'kind':kind,'doc_no':no,'biz_date':date,'qty':qty,'unit_cost_cents':unit,'link_no':link}

def full(docs,every=25):
 """全量重算：从头重放。返回(明细,批次,汇总)或抛出LedgerError。"""
 batches=[];issue_lines={};returned={}
 lines,_=replay(order_docs(docs),0,batches,issue_lines,returned,every)
 return lines,batches,summarize(order_docs(docs),batches,lines)

class Sim:
 """与 services.material.recalc 相同的增量切换逻辑，用内存结构代替数据表。"""
 def __init__(self,every=25):
  self.every=every;self.docs=[];self.processed=[];self.status='ok';self.error=''
  self.batches=[];self.lines=[];self.checkpoints={};self.version=0
 def recalc(self):
  ordered=order_docs(self.docs);prints=fingerprints(ordered)
  if self.status=='ok' and self.processed==prints:return 'noop'
  d=divergence(self.processed,prints)
  cps=[i for i in self.checkpoints if i<d]
  start=max(cps)+1 if cps else 0
  batches=[dict(b) for b in (self.checkpoints[start-1] if cps else [])]
  issue_lines={};returned={}
  for l in self.lines:
   if l['doc_index']<start:
    if l['direction']=='issue':issue_lines.setdefault(l['doc_id'],[]).append(dict(l))
    else:returned[(l['issue_doc_id'],l['issue_line_seq'])]=returned.get((l['issue_doc_id'],l['issue_line_seq']),0)+l['qty']
  try:new_lines,snaps=replay(ordered,start,batches,issue_lines,returned,self.every)
  except LedgerError as exc:
   self.status='error';self.error=str(exc);return 'error'
  self.lines=[l for l in self.lines if l['doc_index']<start]+new_lines
  self.batches=batches
  self.checkpoints={i:s for i,s in self.checkpoints.items() if i<start}
  for i,snap in snaps:self.checkpoints[i]=snap
  self.processed=prints;self.status='ok';self.error='';self.version+=1
  return 'ok'

def lines_key(lines):return sorted((l['doc_id'],l['line_seq'],l['direction'],l['in_doc_id'],l['qty'],l['unit_cost_cents'],l['amount_cents']) for l in lines)
def batches_key(batches):return sorted((b['in_doc_id'],b['qty'],b['unit_cost_cents']) for b in batches)

class FifoTest(unittest.TestCase):
 def test_fifo_order_and_exact_cents(self):
  docs=[doc(1,'in','RK-1','2026-01-01',10,100),doc(2,'in','RK-2','2026-01-02',10,200),doc(3,'out','LJ-1','2026-01-03',15)]
  lines,batches,totals=full(docs)
  self.assertEqual([(l['in_doc_id'],l['qty'],l['amount_cents']) for l in lines],[(1,10,1000),(2,5,1000)])
  self.assertEqual(batches_key(batches),[(1,0,100),(2,5,200)])
  self.assertEqual(totals['issued_cents'],2000)
 def test_same_date_sorted_by_doc_no(self):
  docs=[doc(1,'in','RK-2','2026-01-01',10,200),doc(2,'in','RK-1','2026-01-01',10,100),doc(3,'out','LJ-1','2026-01-02',5)]
  lines,_,_=full(docs)
  self.assertEqual(lines[0]['in_doc_id'],2,'同日期按单号排序，先扣RK-1')
 def test_return_reverse_order_cross_batch(self):
  docs=[doc(1,'in','RK-1','2026-01-01',10,100),doc(2,'in','RK-2','2026-01-02',10,200),doc(3,'out','LJ-1','2026-01-03',15),doc(4,'ret','TL-1','2026-01-04',4,link='LJ-1')]
  lines,batches,totals=full(docs)
  ret=[l for l in lines if l['direction']=='return']
  self.assertEqual([(l['in_doc_id'],l['qty'],l['amount_cents']) for l in ret],[(2,4,800)],'退料先退回最后扣减的批次')
  self.assertEqual(batches_key(batches),[(1,0,100),(2,9,200)])
  self.assertEqual(totals['returned_cents'],800)
 def test_multiple_returns_cumulative_reverse(self):
  docs=[doc(1,'in','RK-1','2026-01-01',10,100),doc(2,'in','RK-2','2026-01-02',10,200),doc(3,'out','LJ-1','2026-01-03',15),doc(4,'ret','TL-1','2026-01-04',4,link='LJ-1'),doc(5,'ret','TL-2','2026-01-05',6,link='LJ-1')]
  lines,batches,totals=full(docs)
  ret=[l for l in lines if l['direction']=='return']
  self.assertEqual([(l['doc_id'],l['in_doc_id'],l['qty']) for l in ret],[(4,2,4),(5,2,1),(5,1,5)],'第二笔退料接着反序退回剩余行')
  self.assertEqual(batches_key(batches),[(1,5,100),(2,10,200)])
  self.assertEqual(totals['on_hand_cents'],5*100+10*200)
 def test_over_return_identifies_first_bad_doc(self):
  docs=[doc(1,'in','RK-1','2026-01-01',10,100),doc(2,'out','LJ-1','2026-01-02',5),doc(3,'ret','TL-1','2026-01-03',3,link='LJ-1'),doc(4,'ret','TL-2','2026-01-04',3,link='LJ-1')]
  with self.assertRaises(LedgerError) as ctx:full(docs)
  self.assertEqual(ctx.exception.doc_no,'TL-2');self.assertEqual(ctx.exception.reason,'超退')
 def test_negative_stock_identifies_doc(self):
  docs=[doc(1,'in','RK-1','2026-01-01',5,100),doc(2,'out','LJ-1','2026-01-02',6)]
  with self.assertRaises(LedgerError) as ctx:full(docs)
  self.assertEqual(ctx.exception.doc_no,'LJ-1');self.assertEqual(ctx.exception.reason,'负库存')
 def test_return_requires_prior_issue(self):
  with self.assertRaises(LedgerError):full([doc(1,'ret','TL-1','2026-01-01',1,link='LJ-9')])
  docs=[doc(1,'in','RK-1','2026-01-01',5,100),doc(2,'ret','TL-1','2026-01-02',1,link='LJ-1'),doc(3,'out','LJ-1','2026-01-03',1)]
  with self.assertRaises(LedgerError) as ctx:full(docs)
  self.assertEqual(ctx.exception.doc_no,'TL-1','退料不得早于原领料生效')
 def test_conservation(self):
  docs=[doc(1,'in','RK-1','2026-01-01',10,120),doc(2,'in','RK-2','2026-01-02',6,135),doc(3,'out','LJ-1','2026-01-03',12),doc(4,'ret','TL-1','2026-01-04',5,link='LJ-1')]
  _,_,totals=full(docs)
  self.assertEqual(totals['on_hand_qty'],totals['inbound_qty']-totals['issued_qty']+totals['returned_qty'])
  self.assertEqual(totals['on_hand_cents'],totals['inbound_cents']-totals['issued_cents']+totals['returned_cents'])

class IncrementalTest(unittest.TestCase):
 def scenario(self,steps,seed,every):
  """乱序补录+跨批退料+随机冲销，每步断言：增量账=全量重算，重跑幂等。"""
  rng=random.Random(seed);sims={'甲':Sim(every),'乙':Sim(every)};next_id=[1]
  def add(m,kind,date,qty,unit=None,link=None):
   d=doc(next_id[0],kind,f'D{next_id[0]:04d}',date,qty,unit,link);next_id[0]+=1;sims[m].docs.append(d);return d
  for step in range(steps):
   m=rng.choice(('甲','乙'));sim=sims[m]
   date=f"2026-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}"
   if sim.status=='error':
    bad=rng.choice(sim.docs);sim.docs.remove(bad)  # 冲销错单或相关单以恢复
   else:
    available=sum(b['qty'] for b in sim.batches)
    open_issues=[d for d in sim.docs if d['kind']=='out' and d['qty']>sum(l['qty'] for l in sim.lines if l['direction']=='return' and l['issue_doc_id']==d['id'])]
    action=rng.choices(['in','out','ret','del'],weights=[34,33,22,11])[0]
    if action=='in':add(m,'in',date,rng.randint(1,40),rng.randint(1,999))
    elif action=='out' and available>0:add(m,'out',date,rng.randint(1,available))
    elif action=='ret' and open_issues:
     target=rng.choice(open_issues)
     left=target['qty']-sum(l['qty'] for l in sim.lines if l['direction']=='return' and l['issue_doc_id']==target['id'])
     later=date if (date,target['doc_no'])>(target['biz_date'],'') else target['biz_date']
     if (later,'D%04d'%next_id[0])<=(target['biz_date'],target['doc_no']):later='2026-12-31'
     add(m,'ret',later,rng.randint(1,left),link=target['doc_no'])
    elif action=='del' and sim.docs:sim.docs.remove(rng.choice(sim.docs))
    else:add(m,'in',date,rng.randint(1,40),rng.randint(1,999))
   sim=sims[m];result=sim.recalc()
   try:
    fl,fb,ft=full(sim.docs,sim.every);ferr=None
   except LedgerError as exc:ferr=str(exc)
   if sim.status=='ok':
    self.assertIsNone(ferr,f'第{step}步增量成功但全量报错：{ferr}')
    self.assertEqual(lines_key(sim.lines),lines_key(fl),f'第{step}步明细不一致')
    self.assertEqual(batches_key(sim.batches),batches_key(fb),f'第{step}步批次不一致')
    self.assertEqual(summarize(order_docs(sim.docs),sim.batches,sim.lines),ft,f'第{step}步汇总不一致')
    self.assertEqual(sim.recalc(),'noop','已生效账重跑必须是幂等空转')
   else:
    self.assertIsNotNone(ferr,'增量报错则全量必须报同一错')
    self.assertEqual(sim.error,ferr,'增量与全量指出的首笔错单必须一致')
  return sims
 def test_incremental_equals_full_random(self):
  self.scenario(steps=260,seed=7,every=25)
 def test_incremental_equals_full_dense_checkpoints(self):
  self.scenario(steps=260,seed=11,every=3)
 def test_backfill_shifts_fifo(self):
  sim=Sim()
  sim.docs=[doc(1,'in','RK-1','2026-01-02',10,200),doc(2,'out','LJ-1','2026-01-03',5)]
  sim.recalc();self.assertEqual(sim.lines[0]['unit_cost_cents'],200)
  sim.docs.append(doc(3,'in','RK-0','2026-01-01',10,100))  # 补录更早入库
  sim.recalc()
  self.assertEqual([l['unit_cost_cents'] for l in sim.lines],[100],'补录旧单后领料改扣最早批次')
  self.assertEqual(sim.version,2)
 def test_delete_and_repost_no_duplicate(self):
  sim=Sim()
  sim.docs=[doc(1,'in','RK-1','2026-01-01',10,100),doc(2,'out','LJ-1','2026-01-02',6)]
  sim.recalc();first=lines_key(sim.lines)
  sim.recalc();sim.recalc()
  self.assertEqual(lines_key(sim.lines),first,'崩溃恢复后重跑不得重复归集')
  sim.docs.remove(sim.docs[1]);sim.recalc()
  self.assertEqual(sim.lines,[]);self.assertEqual(sum(b['qty'] for b in sim.batches),10)

if __name__=='__main__':unittest.main()
