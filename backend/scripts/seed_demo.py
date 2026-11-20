import json,random
from types import SimpleNamespace
from src.config.database import Base,engine,Session
from src.config.settings import CONFIG
from src.models.identity import User
from src.models.source import Source,Policy,Period
from src.models import run,material
from src.models.material import MaterialDoc
from src.utils.security import password_hash
from src.services.validation import validate_source

def demo_rows():
 rng=random.Random(42);rows=[]
 for i in range(240):
  rows.append({'period':'2026-'+('10' if i<120 else '11'),'department':rng.choice(['公共','公共','光学研究','材料研究','工艺研究']),'category':rng.choice(['仪器维护','试验耗材','研究工时']),'amount_cents':rng.randint(1000,500000)})
 return rows

def demo_material_docs():
 """演示跨批领料、反序跨批退料与乱序补录；doc_no自然键幂等。"""
 return [
  {'material':'光学膜料','kind':'in','doc_no':'RK-2026-001','biz_date':'2026-10-08','qty':100,'unit_cost_cents':1200},
  {'material':'光学膜料','kind':'in','doc_no':'RK-2026-002','biz_date':'2026-10-15','qty':60,'unit_cost_cents':1350},
  {'material':'光学膜料','kind':'out','doc_no':'LJ-2026-001','biz_date':'2026-10-20','qty':120},
  {'material':'光学膜料','kind':'ret','doc_no':'TL-2026-001','biz_date':'2026-10-25','qty':30,'link_no':'LJ-2026-001'},
  {'material':'光学膜料','kind':'in','doc_no':'RK-2026-000','biz_date':'2026-10-05','qty':50,'unit_cost_cents':1100},
  {'material':'基材卷材','kind':'in','doc_no':'RK-2026-101','biz_date':'2026-11-02','qty':200,'unit_cost_cents':560},
  {'material':'基材卷材','kind':'out','doc_no':'LJ-2026-101','biz_date':'2026-11-06','qty':80},
  {'material':'封装胶','kind':'in','doc_no':'RK-2026-201','biz_date':'2026-11-10','qty':40,'unit_cost_cents':2300},
  {'material':'封装胶','kind':'out','doc_no':'LJ-2026-201','biz_date':'2026-11-12','qty':10},
  {'material':'封装胶','kind':'ret','doc_no':'TL-2026-201','biz_date':'2026-11-15','qty':4,'link_no':'LJ-2026-201'},
 ]

def seed():
 Base.metadata.create_all(engine)
 with Session() as db:
  for role in ('admin','analyst','viewer'):
   if not db.query(User).filter_by(email=role+'@demo.local').first():db.add(User(email=role+'@demo.local',role=role,password=password_hash('Demo2026!')))
  rows=demo_rows()
  for name in sorted(set(r['period'] for r in rows)):
   if not db.query(Period).filter_by(name=name).first():db.add(Period(name=name,description='合成演示业务期间，seed=42'))
  for i,data in enumerate(rows):
   validate_source(data);key='demo-'+str(i+1)
   if not db.query(Source).filter_by(natural_key=key).first():db.add(Source(natural_key=key,data=data))
  if not db.query(Policy).filter_by(version=CONFIG['policy']['version']).first():db.add(Policy(version=CONFIG['policy']['version'],data=CONFIG['policy']))
  db.commit()
  from src.services.material import post_doc
  actor=SimpleNamespace(email='seed')
  for data in demo_material_docs():
   if not db.query(MaterialDoc).filter_by(doc_no=data['doc_no']).first():post_doc(db,actor,data)
  print(json.dumps({'users':db.query(User).count(),'sources':db.query(Source).count(),'policies':db.query(Policy).count(),'periods':db.query(Period).count(),'material_docs':db.query(MaterialDoc).count()},ensure_ascii=False))
if __name__=='__main__':seed()
