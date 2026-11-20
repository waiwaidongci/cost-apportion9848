import os,logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.config.database import Base,engine,Session
from src.config.settings import CONFIG,REDIS_URL
from src.models import identity,source,run,material
from src.routes import auth,source as source_routes,reports,deliveries,audits,materials
from src.middlewares.errors import Errors
from src.middlewares.rate import RateLimit
@asynccontextmanager
async def lifespan(app):
 Base.metadata.create_all(engine)
 if os.getenv('SEED_DEMO')=='true':
  try:
   from scripts.seed_demo import seed
   seed()
  except Exception: logging.exception('seed失败，可手动重试')
 try:
  from src.services.material import reconcile_all
  with Session() as db: reconcile_all(db)
 except Exception: logging.exception('材料台账启动核对失败，可手动调用 /materials/reconcile')
 yield
app=FastAPI(title=CONFIG['title'],lifespan=lifespan)
app.add_middleware(Errors);app.add_middleware(RateLimit)
for module in (auth,source_routes,reports,deliveries,audits,materials): app.include_router(module.router)
@app.get('/health')
def health():
 from sqlalchemy import text
 import redis
 with engine.connect() as c: c.execute(text('SELECT 1'))
 redis.Redis.from_url(REDIS_URL).ping()
 return {'status':'healthy'}
@app.get('/meta')
def meta(): return CONFIG
