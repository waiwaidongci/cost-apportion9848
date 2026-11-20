# 砺禾项目成本归集簿

内部研究项目工时与费用→精确分摊和透视→站内月结交付；金额用整数分，定时worker站内交付

## 业务场景与工作流
模拟客户：砺禾研究协作组，12位业务与分析人员。每月研究明细先从`cost-apportion-202611.csv`录入底稿，经口径冻结、Python核算、负责人复核后向业务阅读者交付站内CSV。原有流程依靠人工表格抄算，痛点为口径版本难追溯、重复计算易错、复核与交付脱节。

模块：业务总览、业务底稿、新建口径版本、异步核算与复核、定时交付、材料批次账、站内收件箱、审计。底稿可新增/修改/删除；口径仅新增版本；报告提交时冻结来源与版本并保存SHA256。定时交付引用已复核报告快照，worker到期写入数据库，业务阅读者下载。

## 材料批次台账
材料费按实际领料归集。同物料单据按（业务日期，单号）排序：入库产生批次，领料从最早有余量的批次扣减，金额=数量×批次整数分单价；退料按原领料扣减的反序退回原批次与整数分成本。补录旧单或冲销只从该物料最早变动处重算（指纹链定位分歧点+每25笔批次检查点），算完在同一事务一次性切换批次/明细/汇总。出现超退或负库存时不切换，账户进入错单状态并指出首笔错单，已生效领退金额保持不变。每物料事务级咨询锁+账户行锁，并发补录或领退串行，旧结果不得覆盖新账；重算按指纹链幂等，崩溃恢复后启动核对（reconcile）重跑不重复归集。排队报告在提交时快照当时已生效的各物料领退金额，已复核报告照旧。页面可查每张领退单对应的批次与金额，并有"核对增量与全量"按钮用全量重算验证增量账。

核心算法在`backend/src/services/ledger.py`（纯函数，不依赖数据库），编排在`backend/src/services/material.py`；`backend/tests/test_ledger.py`用跨批退料与乱序补录随机序列核对增量与全量一致（`python3 -m unittest discover -s tests`）。接口：`GET/POST /materials…`、`POST/DELETE /material-docs`、`GET /material-docs/{id}/lines`、`POST /materials/{material}/verify`、`POST /materials/reconcile`。单据不可改：更正=冲销后重录。

## 算法口径
按工时权重分摊公共成本、整数分最大余数守恒与差异透视。1分三权重守恒与稳定tie；零权重拒绝；透视总数等于源数。

整数分守恒 · 公共成本逐笔可追溯。输入：业务底稿与口径JSON；输出：summary、透视rows、method、warnings。算法实现在`backend/src/services/calculation.py`，输入校验在`validation.py`。固定seed=42，240条合成数据；未对接真实业务系统。修改源数据和新建因子/口径不会改变已提交报告。

## 一天的验收剧本
1. 09:00 admin查看240条seed底稿与具名业务期间。
2. 09:10 analyst添加`cost-apportion-202611.csv`的一条具名业务记录。
3. 09:20 admin在口径版本页登记新版本；旧版本保留。
4. 09:30 analyst命名“十一月核算”并选择期间/版本排队。
5. 09:31 Redis worker真实执行Python计算，展示汇总/透视与口径边界。
6. 09:40 admin核对数值后填写至少4字复核说明。
7. 09:45 admin建立60秒周期计划，worker到期生成站内持久化交付。
8. 09:46 viewer在站内收件箱下载交付CSV；审计页查看操作者与时间。
9. 09:50 analyst在材料批次账查看seed的跨批领料LJ-2026-001与反序退料TL-2026-001的批次明细，注意补录旧单RK-2026-000已改变领料扣批顺序。
10. 09:55 analyst补录一张更早业务日期的入库单，台账只从最早变动处重算并一次性切换；点“核对增量与全量”确认一致。
11. 10:00 analyst登记超过结存的领料单或超过原领料的退料单，账户指出首笔错单且已生效金额不变；冲销错单后自动恢复。
12. 10:05 analyst再次排队核算，报告快照引用当时已生效的材料领退金额；此前已复核报告照旧。

## 快速启动
```sh
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```
前端 http://localhost:18250 ，后端 http://localhost:19250/docs ，数据库宿主端口17750。中文父目录可用。恰好5服务frontend/backend/worker/db/redis；均有真实healthcheck。停止并清空演示数据：`docker compose down -v --remove-orphans`。

|角色|邮箱|密码|权限|
|---|---|---|---|
|admin|admin@demo.local|Demo2026!|全部底稿、口径版本、核算、复核、调度|
|analyst|analyst@demo.local|Demo2026!|底稿增改删、核算、导出；无复核/调度/口径写权限|
|viewer|viewer@demo.local|Demo2026!|只读；仅可下载已复核报告与站内交付|

## 工程结构与开发
Python3.11/FastAPI/SQLAlchemy/Redis，PostgreSQL16；前端原生HTML/CSS/JS ES modules，Nginx代理`/api/`剥前缀至后端。`frontend/src`按api/stores/pages/components/hooks/utils/router/constants/types拆分；`backend/src`按models/schemas/services/controllers/routes/middlewares/config/utils/constants拆分；`backend/scripts/seed_demo.py`自然键幂等且不覆盖用户修改。SQLAlchemy启动创建初始结构，迁移说明在backend/migrations。

后端开发：在backend安装requirements，设置DATABASE_URL/REDIS_URL/JWT_SECRET，`uvicorn src.main:app --reload`；前端可用Nginx或带同等代理的静态开发服务器。前后端全部业务计算在Python。

环境变量：COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、JWT_SECRET（部署替换）、DATABASE_URL、REDIS_URL、SEED_DEMO。`.env`不入Git。数据库/Redis/共享产物为命名卷。共享角色枚举admin/analyst/viewer与状态queued/running/completed/failed分别定义于backend/src/constants/enums.py和frontend/src/constants/enums.js。两个中间件：统一可恢复校验错误、每IP每分钟360请求限流。

## 已知边界
定时分发为站内收件箱；一名worker轮询执行，无外部邮件。调度发送已复核固定报告快照，不自动重算新数据。时间显示Asia/Shanghai。报告导出适合小型数据；底稿全量加载240行演示数据。Google Fonts不可用时回退serif。后端API以专属字段对象收发，页面通过业务输入控件编辑，不要求用户写JSON。新增来源期间自动可选；专属字段和算法严格校验。JWT演示有效期2小时。材料单据保存时在请求事务内同步重算（演示规模单物料数百笔）；单据只增不改为事件账，更正走冲销重录；退料单的业务日期与单号必须晚于原领料单。

MIT License。

## 实际实体映射
来源记录（Source，专属业务字段校验）、口径版本（Policy）、核算报告（Run）、交付计划（Schedule）、交付（Delivery）均经数据库→模型→请求schema→service→route/controller→frontend API→store→page。Period为已有来源期间字典，在任务期间选择器使用；不单独作为复杂度计数。底稿JSON为小型多字段单记录存储，不虚构未落库的子实体。材料模块：单据（MaterialDoc）、批次现量（MaterialBatch）、领退明细（MaterialLine）、重算检查点（MaterialCheckpoint）、物料账（MaterialAccount）同样全链路落库；报告快照在排队时引用当时已生效的物料账汇总。
