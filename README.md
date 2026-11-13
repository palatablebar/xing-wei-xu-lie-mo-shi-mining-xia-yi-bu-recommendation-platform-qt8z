# nextbest · 行为序列模式挖掘与下一步推荐台

织云 SaaS 增长团队的工作台：把 12 个功能模块的埋点会话变成**可解释的下一步推荐**。
链路是「埋点事件 → 会话序列 → PrefixSpan 模式库 → 下一步推荐 → 运营复核名单 → CSV 导出」。

- 客户场景：增长团队 5 人、12 个功能模块；原来靠看事件表猜下一步、配运营弹窗。
- 解决的三个问题：序列靠猜（改成频繁序列挖掘）、覆盖率低（按用户最近 3 个事件做后缀匹配）、推荐没有置信度（每条推荐带支持度/置信度/提升度）。

## 1. 技术栈与 5 服务

| 服务 | 内容 | 端口（.env） |
| --- | --- | --- |
| `frontend` | Nginx 静态站，原生 HTML/CSS/JS（ES Modules，无框架无构建） | `FRONTEND_PORT=18209` |
| `backend` | FastAPI + SQLAlchemy 2.0，全部计算/校验/持久化在后端 | `BACKEND_PORT=19209` |
| `worker` | Celery worker + beat：心跳与每日增量重挖 | 内网 |
| `db` | MySQL 8.0（utf8mb4） | `DB_PORT=17709` |
| `redis` | 限流计数 + worker 心跳 | 内网 |

```bash
docker compose config --quiet
docker compose up -d --build      # 5/5 healthy 后访问 http://localhost:18209
docker compose exec -T backend python -m scripts.seed_demo   # 幂等，可重复执行
docker compose exec -T backend python -m pytest tests -q
```

## 2. 账号与角色（密码统一 `Demo@2026`）

| 账号 | 角色 | 能做什么 |
| --- | --- | --- |
| `admin@nextbest.io` | 增长平台管理员 | 维护事件字典、发起挖掘、复核推荐、导出 CSV、看审计 |
| `analyst@nextbest.io` | 行为分析专员 | 发起挖掘、复核推荐、导出 CSV；不能改事件字典 |
| `viewer@nextbest.io` | 运营只读 | 只读模式/推荐（用户 ID 脱敏）；不能挖掘、不能复核、不能导出、看不到审计 |

权限不是前端隐藏：低权调用高权接口返回**真实 403**（`src/middlewares/rbac.py`），无 token 401，非法参数 422，
事件码重复 409。视图层再加一层按钮收敛，`site/js/config.js` 的 `PERMISSIONS` 与后端
`src/constants/roles.py` 一一对应。

## 3. 领域实体（8 张表）

| 实体 | 表 | 关键字段 |
| --- | --- | --- |
| `EventDef` 事件口径 | `event_defs` | `code`、`module`、`label`、`is_key`、`weight`、`sample_count`、`enabled` |
| `EventSeq` 会话序列 | `event_seqs` | `session_id`、`user_id`、`events`(JSON)、`event_count`、`started_at`、`converted` |
| `MineRun` 挖掘运行 | `mine_runs` | `run_no`、`min_support_pct`、`max_len`、`top_k`、`status`、`metrics`、`coverage_pct`、`caliber_version_id` |
| `Pattern` 频繁序列 | `patterns` | `items`(JSON)、`length`、`support_count`、`support_pct`、`confidence`、`lift`、`rank` |
| `Recommendation` 下一步推荐 | `recommendations` | `user_id`、`suffix`(JSON)、`next_event`、`confidence`、`lift`、`score`、`priority`、`status` |
| `CaliberDraft` 口径草稿 | `caliber_drafts` | `status`、`changes`(JSON)、`base_version_id`、`created_by`、`published_at` |
| `CaliberRehearsal` 口径预演 | `caliber_rehearsals` | `draft_id`、`status`、`changes_snapshot`(JSON)、`impact`(JSON) |
| `CaliberVersion` 口径版本 | `caliber_versions` | `version_no`、`status`、`snapshot`(JSON)、`changed_codes`、`rehearsal_summary`、`published_by` |

### 3.1 口径变更为什么要走「草稿 → 预演 → 发布」

`is_key` / `enabled` 是挖掘与推荐的口径开关：停用或非关键事件会被排除在模式库和推荐名单之外。
直接 PATCH 正式字典会让「旧模式生成的名单」瞬间失效，而导出又用最新事件名重写历史内容，造成口径半新半旧。
因此这两个标记不再直写 `event_defs`，而是进入版本化流程：

1. **入草稿**：修改关键/停用标记只写 `caliber_drafts`（全表仅一条 active），正式字典与已有名单不变；权重等非口径字段仍即时更新。
2. **预演**：在内存里按草稿口径重跑 PrefixSpan + 推荐，输出**受影响会话数、新模式数、新推荐名单样例、被排除动作**，不写 `patterns` / `recommendations`。
3. **确认后统一发布**：单事务内切 `event_defs` 并落一条不可变 `CaliberVersion`；任一步失败整体回滚，正式口径保持旧版，不允许半新半旧。
4. **未生效前按旧口径**：预演不产生正式数据；复核与 CSV 导出始终读取已落库名单，并带生成时的口径版本号。
5. **回滚**：把 `event_defs` 还原到上一版本快照，当前版本标记 `rolled_back`（首版无更早基线，拒绝回滚）。

每个实体贯穿「表 → model → schema → service → controller → route → 前端 api → 页面」，
DDL 参考见 `backend/migrations/001_core_tables.sql`。

## 4. 算法口径（后端 Python 真算，前端只展示）

纯函数在 `backend/src/services/prefixspan.py` 与 `backend/src/services/recommender.py`，不碰 DB，可直接单测。

### 4.1 算法 A｜PrefixSpan 频繁序列挖掘

- 最小支持度 `min_support_pct=3%`：按会话数向上取整 → 600 条会话 ⇒ **18 条会话**；
- 最大长度 `max_len=5`；只收长度 ≥ 2 的序列（单个事件不构成行为路径）；
- 支持度 = 命中会话数 / 参与挖掘的会话数；模式库按支持度倒序保留 `top_k=50` 条；
- 置信度 = 命中会话数 / 去掉末位事件后的前缀命中会话数（P(下一步 | 前缀)）；
- 提升度 = 置信度 / 末位事件在全部会话中的占比。

### 4.2 算法 B｜下一步推荐

- **口径过滤先行**：会话事件先剔除「停用（`enabled=false`）或非关键（`is_key=false`）」的动作，剩下的才进入挖掘与推荐；过滤后为空的会话不入模。当前生效口径 = 最近一条 published `CaliberVersion`（见 3.1）。
- 每位活跃用户取最近一条含有效事件会话的最后 `k=3` 个事件作为后缀（不足 3 个按实际长度）；
- 候选模式：模式前缀尾部与后缀逐位相等（优先 3 位，其次 2 位、1 位），推荐事件 = 模式末位事件；
- 同一模式只出一条；分数 = **置信度 × 提升度**，按分数倒序；
- 同模块最多 2 条、每用户最多 6 条（`MAX_PER_MODULE` / `MAX_PER_USER`）；
- 优先级：分数 ≥1.2 高、≥0.7 中、其余低；
- 覆盖率 = 有推荐产出的用户数 / 活跃用户数。

> 结果全部落库（`patterns` / `recommendations`），前端只做展示与筛选，不参与任何计算。
> 每次 `MineRun` 在 `metrics` 里记录 `caliber_version_no`、`excluded_event_codes` 与 `caliber_affected_sessions`，可追溯名单基于哪一版口径。

## 5. API

| 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- |
| POST | `/api/auth/login` | 邮箱+密码换 JWT | 公开 |
| GET | `/api/auth/me` | 当前用户 | 登录 |
| GET | `/api/overview` | 会话数/覆盖率/模式数/信号瀑布 | 三角色 |
| GET/POST/PATCH | `/api/events`、`/api/events/{id}` | 事件字典 | 读三角色，写仅 admin（PATCH 中 is_key/enabled 自动转草稿，不直写） |
| GET | `/api/caliber/state` | 待发布草稿 vs 正式口径差异 | 三角色 |
| GET | `/api/caliber/draft` | 取/建当前活跃草稿 | 仅 admin |
| POST | `/api/caliber/draft/stage` | 关键/停用变更写入草稿 | 仅 admin |
| POST | `/api/caliber/draft/{id}/discard` | 作废草稿 | 仅 admin |
| POST | `/api/caliber/draft/{id}/rehearse` | 预演影响面（受影响会话/模式/名单） | 仅 admin |
| GET | `/api/caliber/rehearsals/{id}` | 预演结果 | 三角色 |
| POST | `/api/caliber/draft/{id}/publish/{rehearsal_id}` | 统一发布口径版本（单事务，失败回滚） | 仅 admin |
| GET | `/api/caliber/versions`、`/versions/{id}` | 口径版本列表/快照差异 | 三角色 |
| POST | `/api/caliber/versions/{id}/rollback` | 回滚到上一版口径 | 仅 admin |
| GET | `/api/sequences`、`/api/sequences/{id}`、`/api/sequences/stats` | 会话序列浏览 | 三角色（viewer 脱敏） |
| GET/POST | `/api/mine-runs`、`/api/mine-runs/{id}` | 挖掘运行 | 读三角色，发起 admin+analyst |
| GET | `/api/patterns`、`/api/patterns/distribution` | 模式库 | 三角色 |
| GET | `/api/recommendations`、`/api/recommendations/{id}` | 推荐名单 | 三角色（viewer 脱敏） |
| PATCH | `/api/recommendations/{id}/review` | 复核采纳/驳回 | admin+analyst（viewer 403） |
| GET | `/api/exports/recommendations.csv`、`patterns.csv`、`mine-runs.csv` | CSV 导出 | admin+analyst（viewer 403） |
| GET | `/api/audit` | 审计日志 | 仅 admin |
| GET | `/api/health` | 健康检查（db/redis/worker 心跳） | 公开 |

## 6. 页面（原生 ES Modules）

1. `#/login` 登录（信号 scope + 操作员终端版式）
2. `#/overview` 总览：四条仪器读数 + 口径版本块（待发布 vs 正式）+ **信号瀑布**（12 个时间桶 × 6 模块堆叠）+ 模块事件量 + 模式支持度阶梯
3. `#/events` 事件字典（列表 + 抽屉详情 + admin 改口径/登记；关键/停用标记入草稿，顶部待发布横幅 + 口径发布台）
4. `#/sequences` 序列浏览（筛选 + 事件轨道 chip + 抽屉全文）
5. `#/mining` 模式挖掘（运行列表带口径版本 + 发起挖掘 + 参数口径 + 模式库阶梯/表格 + 导出）
6. `#/recommendations` 推荐名单（筛选 + 抽屉复核 + 导出 CSV；页头显示名单所属口径版本）
7. `#/audit` 审计日志（仅 admin；可按口径动作筛选，顶部提示待发布草稿）

共用组件：`site/js/ui.js` 的 `table` / `drawer` / `field` / `readouts` / `waterfall` / `track` / `ladder` / `badge`。

## 7. 共享枚举出现位置（改动需两侧同步）

| 枚举 | 后端 | 前端 |
| --- | --- | --- |
| 6 个模块 `account/integration/board/report/alert/billing` | `backend/src/constants/enums.py::Module`、`MODULE_LABELS` | `site/js/config.js::ENUMS.module` |
| 挖掘状态 `queued/running/success/partial/failed` | `enums.py::MineStatus`、`MINE_STATUS_LABELS` | `ENUMS.mineStatus`、`config.js::statusTone` |
| 触发方式 `manual/schedule/seed` | `enums.py::TriggerKind`、`TRIGGER_LABELS` | `ENUMS.trigger` |
| 复核状态 `pending/confirmed/dismissed` | `enums.py::ReviewStatus`、`REVIEW_STATUS_LABELS` | `ENUMS.reviewStatus`、`reviewTone` |
| 优先级 `high/medium/low` | `enums.py::RecPriority`、`REC_PRIORITY_LABELS` | `ENUMS.priority`、`badgeTone` |
| 角色 `admin/analyst/viewer` | `enums.py::Role`、`constants/roles.py` | `config.js::ROLE_LABELS/PERMISSIONS` |

## 8. seed（幂等）

`backend/scripts/demo_data.py` 用固定 seed + 会话序号生成确定性数据（无网络、无随机漂移）：
**12 个事件、600 条会话（均值约 8 事件）、90 条转化会话、1 次初始化挖掘**。
`backend/scripts/seed_demo.py` 按自然键 upsert：`users.email`、`event_defs.code`、`event_seqs.session_id`、
`mine_runs.seed_key`、`patterns(run_id, seq_key)`、`recommendations(run_id, user_id, pattern_id, next_event)`、
`audit_logs.seed_key`；重复执行不新增记录、不覆盖人工复核过的推荐状态。
首次 seed 额外建立一条初始口径版本 `C00000000-000`（`CaliberVersion` 基线，幂等），作为后续发布与回滚的快照起点。

结束时打印一行（两次执行逐字一致）：

```
SEED_SUMMARY brand=nextbest users=3 sources=<事件口径数> runs=<挖掘运行数> findings=<模式数> pending=<待复核推荐数>
```

`sources` 对应事件字典数量，`runs` 对应挖掘运行数，`findings` 对应模式库条数，`pending` 对应待复核推荐数。

## 9. 测试

```bash
docker compose exec -T backend python -m pytest tests -q     # 算法 + 安全工具单测
BASE_URL=http://localhost:18209 node ../test-artifacts/gb-610/tests/smoke.mjs
BASE_URL=http://localhost:18209 node ../test-artifacts/gb-610/tests/screenshots.cjs
```

- `backend/tests/test_prefixspan.py`：频次门槛、边界（等于最小计数入选 / 少一条落选）、长度上限、top_k 截断、置信度与提升度算术、单事件不计、空输入、确定性；
- `backend/tests/test_recommender.py`：后缀匹配、不推荐刚做过的动作、无匹配返回空、按分数排序、同模块 ≤2、每用户 ≤6、覆盖率、优先级分档；
- `backend/tests/test_caliber.py`：口径过滤（停用/非关键排除）、受影响会话统计、草稿差异识别、目标口径合并、后缀在空会话下不错位、k 上限；
- `backend/tests/test_security.py`：密码哈希、JWT 往返、非法 token。
- 真机结果（含 seed 两次原文、pytest、smoke、403、关键数值、截图清单）记录在
  `batch-20261113/test-artifacts/gb-610/TESTING.md`。

## 10. 横切能力

- **JWT 三角色**：`middlewares/auth.py` 解析 `Authorization: Bearer`，`rbac.py` 给每个路由挂角色依赖；
- **审计**：`middlewares/audit_logger.py` 记录所有写请求（layer=`http`），controller 再记领域动作（layer=`domain`），worker 记 `layer=worker`；口径生命周期动作 `event.stage` / `caliber.rehearse` / `caliber.publish` / `caliber.rollback` / `event.draft_discard` 均留痕；
- **限流**：`middlewares/rate_limit.py` Redis 固定窗口，读 300/min、写 60/min（`/events`、`/caliber`、`/mine-runs`、`/recommendations`、`/exports`）；
- **CSV 导出**：`utils/csv_export.py`（UTF-8 BOM），三个导出端点都写审计；导出首列为口径版本号，只含已发布口径生成的正式名单；
- **口径事务一致性**：发布与回滚在单事务内完成（改 `event_defs` + 写/改 `CaliberVersion` + 收口草稿预演），异常整体回滚，杜绝半新半旧；预演纯内存模拟，不触碰正式库；
- **worker 心跳**：Celery beat 周期任务写 Redis，`/api/health` 与总览 ticker 读取，>120s 视为超时。

## 11. 视觉方向

时序信号台：深墨绿底（`oklch(0.185 0.026 167)`）+ 荧光橙读数（`oklch(0.755 0.185 55)`）+ 网格坐标 +
等宽字（`IBM Plex Mono`）+ 标题字（`Space Grotesk`）。总览用「信号瀑布」而非卡片墙，登录页用 scope/终端版式。
色板与字体定义在 `frontend/site/css/tokens.css`，离线时回退 `PingFang SC` / `SFMono-Regular`。

## 12. 已知边界

- 合成埋点数据（无真实客户埋点），会话时长与转化规则是演示口径；
- 模式库按支持度倒序截断 top_k（默认 50），更长的稀有路径不会进入推荐候选；
- 定时重挖用 Celery beat 触发，只跑一次全量，未做增量窗口与断点续算。
