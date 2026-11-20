# 002 材料批次台账

SQLAlchemy启动创建以下业务表：

- `materialdocs`：材料单据事件（入库in/领料out/退料ret），`doc_no`全局唯一，重复提交不会产生新单；退料以`link_no`引用原领料单。
- `materialbatches`：批次现量（每个入库单一批次，剩余数量随领退增减）。
- `materiallines`：领退归集明细（单据×批次×数量×整数分金额；退料行记录原领料单与行号）。
- `materialcheckpoints`：增量重算检查点（每25笔单据快照批次状态）。
- `materialaccounts`：物料账（版本、状态、首笔错单、已生效指纹链、汇总、上次重算区间）。

升级：备份后启动即自动建表；既有表结构不变。重算只写以上五表且与单据同事务提交，崩溃恢复后由`reconcile`按指纹链幂等核对。
