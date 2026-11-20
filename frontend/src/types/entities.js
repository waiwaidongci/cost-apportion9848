// API实体字段约定：来源{id,natural_key,data}、口径{id,version,data}、报告{id,status,snapshot,checksum,result,approved}、计划{next_at,enabled}、物料账{material,version,status,totals,recalc}、材料单据{id,kind,doc_no,biz_date,qty,allocated_cents}、批次行{batch_doc_no,direction,qty,amount_cents}。
export const ENTITY_KEYS=['sources','policies','runs','schedules','deliveries','materials'];
