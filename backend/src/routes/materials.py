from fastapi import APIRouter,Depends
from src.config.database import database
from src.controllers.auth import current,editor,admin
from src.schemas.requests import DataInput
from src.services import material as svc
router=APIRouter()
@router.get('/materials')
def accounts(db=Depends(database),u=Depends(current)): return svc.list_accounts(db)
@router.get('/materials/{material}/detail')
def detail(material:str,db=Depends(database),u=Depends(current)): return svc.detail(db,material)
@router.post('/material-docs')
def post(b:DataInput,db=Depends(database),u=Depends(editor)):
 account,info=svc.post_doc(db,u,b.data)
 return {'account':svc.account_view(account),'recalc':info}
@router.delete('/material-docs/{doc_id}')
def delete(doc_id:int,db=Depends(database),u=Depends(editor)):
 account,info=svc.delete_doc(db,u,doc_id)
 return {'account':svc.account_view(account),'recalc':info}
@router.get('/material-docs/{doc_id}/lines')
def lines(doc_id:int,db=Depends(database),u=Depends(current)): return svc.doc_lines(db,doc_id)
@router.post('/materials/{material}/verify')
def verify(material:str,db=Depends(database),u=Depends(current)): return svc.verify(db,u,material)
@router.post('/materials/reconcile')
def reconcile(db=Depends(database),u=Depends(admin)): return {'reconciled':svc.reconcile_all(db,u.email)}
