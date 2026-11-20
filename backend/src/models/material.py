from sqlalchemy import Column,Integer,String,JSON,Text,Float
from src.config.database import Base
class MaterialDoc(Base):
 __tablename__='materialdocs'
 id=Column(Integer,primary_key=True);material=Column(String(60),index=True);kind=Column(String(8));doc_no=Column(String(64),unique=True);biz_date=Column(String(10));qty=Column(Integer);unit_cost_cents=Column(Integer,nullable=True);link_no=Column(String(64),nullable=True);actor=Column(String(120));created=Column(Float)
class MaterialBatch(Base):
 __tablename__='materialbatches'
 id=Column(Integer,primary_key=True);material=Column(String(60),index=True);in_doc_id=Column(Integer);doc_no=Column(String(64));biz_date=Column(String(10));unit_cost_cents=Column(Integer);qty=Column(Integer)
class MaterialLine(Base):
 __tablename__='materiallines'
 id=Column(Integer,primary_key=True);material=Column(String(60),index=True);doc_id=Column(Integer,index=True);doc_index=Column(Integer);line_seq=Column(Integer);direction=Column(String(8));in_doc_id=Column(Integer);issue_doc_id=Column(Integer);issue_line_seq=Column(Integer);qty=Column(Integer);unit_cost_cents=Column(Integer);amount_cents=Column(Integer)
class MaterialCheckpoint(Base):
 __tablename__='materialcheckpoints'
 id=Column(Integer,primary_key=True);material=Column(String(60),index=True);doc_index=Column(Integer);doc_id=Column(Integer);batches=Column(JSON)
class MaterialAccount(Base):
 __tablename__='materialaccounts'
 material=Column(String(60),primary_key=True);version=Column(Integer,default=0);status=Column(String(8),default='ok');error=Column(Text,default='');processed=Column(JSON,default=list);totals=Column(JSON,default=dict);recalc=Column(JSON,default=dict);updated=Column(Float,default=0)
