# Pull-Based Job Dispatch — 設計文件 v2

**日期：** 2026-07-13
**狀態：** Accepted（經全面重審訪談定案；v1 見 git 歷史前的 `docs/superpowers/`，已廢棄）
**範圍：** Back-End + Sandbox（Runner）；meta-repo compose
**相關決策：** [ADR-0001](../adr/0001-pull-based-dispatch-over-http.md)（pull over HTTP）、[ADR-0002](../adr/0002-per-job-lease.md)（per-job lease）、[ADR-0003](../adr/0003-result-landing-invariant.md)（落地不變量）、[ADR-0004](../adr/0004-ephemeral-runner-identity.md)（短暫身分）
**詞彙：** 見根目錄 [CONTEXT.md](../../CONTEXT.md)（Runner / Job / Lease / Orphan / Reclaim / Executor / Drain 等定義以該檔為準）

---

## 1. 問題與動機

現行 dispatch flow 有三個獨立破口，導致 submission 卡在 `status=-1`（Pending）永不更新：

| 破口 | 現況 | 失效後果 |
|---|---|---|
| ① Backend → Sandbox `POST /submit/<id>` | 同步 HTTP，無 timeout、無 retry | Sandbox 沒回 → worker hang；4xx/5xx 只 log |
| ② Sandbox 內部處理 | 純 in-memory；worker thread 無保護 | thread crash → callback 永遠不來 |
| ③ Sandbox → Backend callback | 單次嘗試 | backend 沒收到 → 永遠 Pending |

Backend 沒有排程器、health check、stuck submission 偵測。

## 2. Goals 與 Non-Goals

### Goals
- **G1** 消滅 submission 卡 Pending（所有 runner 失效情境有自動復原路徑）
- **G2** Runner 自我註冊；加新 runner 只需一個 registration token
- **G3** 為「考試前手動擴增 runner、考後關機」運維模式鋪路
- **G4** 單一 dispatch path，不長期維護兩套
- **G5** 交付產物可分段 review（每個 PR 是自足、可理解的小單位）

### Non-Goals
- **N1** Per-testcase 粒度分散（Job = submission 的一次評測）
- **N2** AWS auto-scaling 完整實作（鋪路即可）
- **N3** Runner zombie 偵測（per-job lease 已鋪 hook，v2 再補 watchdog）
- **N4** 進階 admin UI（v1 提供最小 admin API，見 §7.6）
- **N5** 新增 MongoDB collection（transient 狀態全在 Redis）
- **N6** 判題 dispatch 不擴展為通用 task queue；未來寄信/MOSS 用 in-stack Celery/RQ + 現有 Redis 另行立案
- **N7** Frontend「Sandbox 設定」頁暫不處理（backend 移除其依賴的 endpoint 後該頁失效；以 issue 追蹤）

### User Stories

**學生（提交者）**
1. As a 學生, I want 提交後在有限時間內拿到判題結果或明確的錯誤狀態（JE）, so that 我不會對著永遠 Pending 的提交乾等。
2. As a 學生, I want 某台 runner 故障時我的提交自動由其他 runner 接手重跑, so that 基礎設施故障不影響我的成績與繳交期限。
3. As a 學生, I want 長時間執行的提交（大測資）不會被誤判為故障而中斷, so that 合法的長程式能正常完成判題。
4. As a 學生, I want 考試尖峰時提交依序被消化（FIFO）, so that 我的提交不會被插隊或遺失。

**教師 / 課程管理者**
5. As a 教師, I want 修正測資後批次 rejudge 整題, so that 全部學生的成績以新測資為準。
6. As a 教師, I want rejudge 撞上進行中的判題時，最終成績必為新一輪的結果, so that 不會出現過時結果覆蓋新結果。
7. As a 教師, I want 被標成 JE 的提交可用 rejudge 救回, so that 暫時性基礎設施問題不會永久影響成績。

**系統管理員 / 運維**
8. As a 系統管理員, I want 開新機器、給一個 registration token 就加入判題叢集, so that 考試前擴增不需進 admin UI 或改設定。
9. As a 系統管理員, I want 考試後對 runner 直接下關機（drain）, so that 進行中的判題不遺失、未開始的立即轉給其他 runner。
10. As a 系統管理員, I want 透過 admin API 看到所有 runner 的存活狀態與持有工作, so that 考試中能即時掌握判題容量。
11. As a 系統管理員, I want 個別撤銷某台失控或外洩的 runner, so that 不必全機隊換密鑰重啟。
12. As a 系統管理員, I want 死亡 runner 的紀錄自動消失, so that 管理視圖不被歷史殘骸淹沒。
13. As a 系統管理員, I want Redis 或 backend 重啟後系統自動收斂回正常, so that 深夜故障不需人工介入。

**維護者**
14. As a 後端維護者, I want 每個變更以小而自足、獨立綠燈的 PR 交付, so that review 品質與速度可控。
15. As a 後端維護者, I want 系統行為由核心不變量（INV1–5）定義且各有對應測試, so that 重構時能快速驗證正確性未被破壞。

## 3. 決策摘要

| 決策點 | 選擇 | 依據 |
|---|---|---|
| Dispatch 外形 | Pull over HTTP（runner 出站短輪詢） | ADR-0001 |
| 租約 | Per-job lease；lease 過期 = orphan 唯一判準 | ADR-0002 |
| 落地保護 | completing 狀態 + 落地不變量（無 je_pending） | ADR-0003 |
| 身分 | 短暫身分 + TTL 回收 + 401 fail-fast | ADR-0004 |
| Rejudge 併發 | current_job currency + runner 端 job_id keying | §9、§10 |
| Abort | 保留，依原因計數 | §7.5 |
| 基底 | 手寫 Redis 結構 + Lua | ADR-0002 附帶 |
| 交付 | Small CLs / dark-launch（keystone 切換） | §15 |
| 部署 | 維護時段一次切換；卡住的用 rejudge 救 | §15.3 |

## 4. 架構總覽

```
Browser ─► Backend (Flask) ── enqueue ──► Redis（queue + lease + 身分）
              ▲                              ▲
              │ Runner API（全部由 runner 發起）│
              │  POST /runners/register        │
              │  POST /runners/<rn>/heartbeat ─┘（夾帶 active_job_ids 續租）
              │  GET  /runners/<rn>/next-job
              │  PUT  /runners/<rn>/jobs/<jb>/complete
              │  PUT  /runners/<rn>/jobs/<jb>/abort
              │  GET  /runners（admin）
              │
   Runner #1..N（原 Sandbox；動態註冊，出站連線，NAT 後可用）
     ├ runner/    協調層：registration / heartbeat / poller / result_sender / client
     └ executor/  執行層：docker 容器編譯執行（原 runner/submission.py 等，改名）
```

最終結果由 complete 寫回 Mongo `Submission`；Mongo schema 不變（廢欄位留待 PG 遷移清理）。

## 5. ID 與 Token 規範

| 類型 | Prefix | 產生 |
|---|---|---|
| Runner ID | `rn_` | ULID |
| Runner Token | `rk_` | `secrets.token_urlsafe(32)` |
| Job ID | `jb_` | ULID |

預留：`ak_` admin key、`uk_` user API key、`sn_` submission、`pb_` problem。

## 6. 核心不變量

Review 與測試以此清單為地圖；每條不變量在 §9 狀態機各有對應轉移。

- **INV1（落地）**：Job 從 Redis 消失的唯一途徑是最終結果（成績或 JE）已成功寫入 Mongo。
- **INV2（orphan）**：lease 過期是 Orphan 的唯一判準；runner 死活不參與判定。
- **INV3（單寫者）**：同一 Job 至多一個 complete 寫入成功（completing 狀態 + per-submission lock）。
- **INV4（currency）**：非 current job 的結果一律丟棄——回 `204`、必記 log，不觸發 runner retry。
- **INV5（收斂）**：attempts 單調遞增（claim/reclaim/計數性 abort），達 `MAX_ATTEMPTS` 收斂為 JE，不存在無限重試路徑。

## 7. API 規格

所有 runner endpoints 掛在 `/runners` prefix（Caddy 將 `/api/*` rewrite 至 backend）。除 register 外，皆需 `Authorization: Bearer rk_...` 並驗證與 URL 中 `runner_id` 的對應（`@require_runner_token`）。

### 7.1 `POST /runners/register`
Body：`{"registration_token": "...", "name": "runner-ec2-1"}`。
回 `201`：`{"runner_id", "token", "config": {"heartbeat_interval_sec": 15, "poll_interval_sec": 3, "max_concurrent_jobs": 8}}`；token 不對回 `401`。
Backend 動作：發 `rn_id`/`rk_token`（只存 SHA-256）、寫 meta（name、registered_at、ip）帶 7d TTL、`ZADD runners:registered <now> <rn_id>`；順手清 ZSET 中 score 老於 7 天的成員及其 keys。

### 7.2 `POST /runners/<rn>/heartbeat`
Body：`{"active_job_ids": ["jb_...", ...]}`。回 `204`。
Backend 動作：`ZADD runners:registered <now>`、meta/token keys 續 TTL、對每個 active job 驗 `leased_by == rn` 後更新 `lease_deadline = now + 30s`（Lua）。不在列表中的 job 續租自然停止 → 過期成為 Orphan（INV2）。

### 7.3 `GET /runners/<rn>/next-job`
回 `200` + payload 或 `204`（無工作）。
Backend 邏輯順序：
1. **時間閘 orphan 掃描**：距上次掃描 >15s（`SET NX EX` 防同時掃）→ 掃 `jobs:leased` 中 lease 過期者；attempts 未滿 → 原子 reclaim 給呼叫者直接回傳；已滿 → 標 JE 寫 Mongo，成功才刪（INV1、INV5）。
2. `RPOP jobs:pending`；取出後檢查 currency——非 current 直接銷毀該 job、繼續取下一個（INV4 的派發端）。
3. 都沒有 → `204`。

Payload：`{"job_id", "submission_id", "problem_id", "language", "code_url", "checker", "tasks": [...]}`。`code_url` 於 handler 內即時簽發（1hr presigned URL），不落 Redis。

### 7.4 `PUT /runners/<rn>/jobs/<jb>/complete`
Body：`{"tasks": [...]}`（shape 同現行 callback）。
回應：`204` 成功；`204` + log「stale result dropped」若非 current（INV4）；`409` 已被 reclaim（runner 應 drop）；`404` job 不存在；`401` token 錯。
流程（per-submission lock 內）：驗 ownership → 驗 currency → 標 `state=completing` → `process_result` 寫 Mongo → 成功後刪 job、清 current_job（INV1、INV3）。寫入拋例外 → 還原狀態，runner 依 retry 規則重送。

### 7.5 `PUT /runners/<rn>/jobs/<jb>/abort`
Body：`{"reason": "drain" | "prep_failed" | "rejected"}`。回 `202`；`409`/`404` 同上。
語意：清 lease、推回 pending 隊尾。**`drain` 不計 attempts**（rolling restart 不得折損 job 壽命）；`prep_failed`/`rejected` 計入（poison 收斂路徑，INV5）。計數後達上限 → 標 JE（走 INV1 流程）。

### 7.6 `GET /runners`（admin-only，`@login_required` + admin 權限）
列出 ZSET 成員：`[{"runner_id", "name", "last_seen", "alive", "active_jobs": [...]}]`。資料來源為 backend 記帳（非自報）。

### Runner retry 規則
complete/abort 除 `2xx`/`409`/`404` 外皆 retry（exponential backoff，上限 5 次）；耗盡後保留本地備份（`file_manager.backup_data`）並放棄——lease 過期後由 reclaim 重跑兜底。

## 8. Redis Schema

```
# 身分（軟狀態，可整體重建；ADR-0004）
runners:registered            ZSET    member=rn_id, score=最後 heartbeat epoch
runner:<rn>:meta              HASH    {name, registered_at, registration_ip}   TTL 7d
runner:<rn>:token_hash        STRING  SHA256(rk_token)                          TTL 7d
runner:<rn>:alive             STRING  "1" TTL 30s —— 純監控顯示，不參與任何判定

# Job
jobs:pending                  LIST    待領 jb_id（LPUSH 進 / RPOP 出）
jobs:leased                   SET     已租出 jb_id
job:<jb>                      HASH    {submission_id, problem_id, language,
                                       code_minio_path, checker, tasks_meta_json,
                                       leased_by, lease_deadline, state, attempts,
                                       created_at, last_error}
submission:<sid>:current_job  STRING  currency 指標（INV4）
submission:<sid>:job_lock     lock    SET NX EX，per-submission 序列化（INV3）
dispatch:last_recovery        STRING  時間閘（SET NX EX 15）
```

無 `je_pending`（ADR-0003）、無 claim 計數器（時間閘取代）。Lua scripts 一一對應狀態轉移：`claim_pending`（含 currency 銷毀）、`renew_lease`、`reclaim_expired`（含 attempts 檢查，耗盡回 -1 且**不移除**）、`abort_requeue`（含依 reason 計數）。

## 9. Job 狀態機

```
enqueue ─► pending ─claim─► leased ─complete─► completing ─Mongo OK─► (刪除)
              ▲               │  ▲                  │
              │             lease │                 └─Mongo 失敗─► 還原 leased，等 retry/過期
              │             過期  │
              │               ▼   │
              └──abort────  orphan┴─reclaim（attempts+1）─► leased（新 runner）
              （隊尾）        │
                             └─attempts ≥ MAX ─► 標 JE 寫 Mongo ─成功─► (刪除)
                                                        └─失敗─► 留在原地，下次掃描重試（INV1）
```

觸發點整理：續租失敗/停止 → 過期（INV2）；掃描由 next-job 的 15s 時間閘驅動；`completing` 中 backend crash → job 留在 Redis、lease 過期後可被 reclaim 重跑（`process_result` 容忍重算，見 §17）。

## 10. Runner 內部結構

```
main.py（docker CMD；Flask 完全移除，無 HTTP server）
├ 讀 config → POST register（失敗以 backoff 1→2→4→8→16→30s 重試；401 不重試直接退出）
├ heartbeat thread：每 15s POST，body 帶 ActiveJobTracker 快照；連續 2 次 401 → fail-fast
├ poller thread：有容量才 GET next-job → 下載 code → 準備目錄 → dispatcher.handle(job)
│    prep 失敗：本地重試 3 次（backoff）→ abort(reason=prep_failed)
├ dispatcher（executor/ 之上的既有編排，最小修改）：完成時 push JobResult 到 result_queue
└ result_sender thread：PUT complete（retry 規則見 §7）；400 拒收 → abort(reason=rejected)

SIGTERM（drain）：停止 poll → 未開始的 job abort(reason=drain) → 等 in-flight 跑完
→ result_queue 清空 → 退出。docker stop --time=600。
401 fail-fast：行程直接退出，交由 compose restart policy 重生（重生即重新註冊新身分）。
```

**模組佈局**：新協調層放 `runner/`（client.py、registration.py、heartbeat.py、poller.py、result_sender.py、active_jobs.py、config.py）；既有容器執行層（現 `runner/submission.py`、`runner/sandbox.py`）改名 `executor/`。

**job_id keying（關鍵改動）**：工作目錄、容器命名、dispatcher 內部字典（locks/result/created_at）全部以 `job_id` 為 key。同 submission 的多個 job 是**合法並行狀態**（rejudge 撞窗口時發生，見 §12），`DuplicatedSubmissionIdError` 防線與 `prepare_submission_dir` 的 FileExistsError 特判整組刪除。

環境變數：`BACKEND_URL`（統一命名，`BACKEND_API` 刪除）、`RUNNER_REGISTRATION_TOKEN`、`RUNNER_NAME`（選填，log/admin 顯示用穩定名）、`MAX_CONTAINER_NUMBER` 等沿用。`SANDBOX_TOKEN` 死碼刪除。

## 11. Backend 內部結構

```
dispatch/           # Redis-based，全新模組
├ config.py         # 參數（見 §13）
├ redis_keys.py     # 集中 key 命名
├ runner.py         # register / verify_token / GC / list_runners
├ job.py            # enqueue / claim / renew / reclaim / complete / abort
└ scripts.py        # Lua（一支對應一條狀態轉移）

model/runner.py     # Blueprint 6 endpoints（§7）
model/schemas/runner.py、model/utils/runner_auth.py
```

`mongo/submission.py`：`submit()`/`rejudge()` 改呼叫 `enqueue_job`（`TESTING`/`handwritten` 跳過不變）；移除 `send()`、`target_sandbox()`、`sandbox_resp_handler()`、per-submission token。整檔刪除 `mongo/sandbox.py`；移除舊 `PUT /submission/<id>/complete` 與 `PUT /config` 的 sandbox_instances 管理（`SubmissionConfig.sandbox_instances` 欄位本身留待 PG 遷移清）。

## 12. Failure Modes

| 情境 | 偵測 | 復原 | 使用者體感 |
|---|---|---|---|
| Runner 斷電/crash | 續租停 → lease 30s 過期 | 15s 內下個時間閘掃描 reclaim | Pending +30~45s |
| Worker thread 悄死（行程活著） | 該 job 不在 active_job_ids → 續租停 | 同上 | 同上 |
| Runner 網路斷 <15s | 漏 1 次 heartbeat，lease 未過期 | 無需 | 無感 |
| Backend 短暫 down | Runner heartbeat/poll retry | 自動 | Pending 略增 |
| Backend 寫結果時 crash | job 停在 completing、lease 過期 | reclaim 重跑（結果重算） | Pending +一輪 |
| Redis 重啟（AOF on） | 最多掉 1s 寫入 | 身分軟狀態自癒（401→fail-fast→重註冊）；極少數 job 遺失用 rejudge 救 | 罕見 |
| MinIO 短暫不可用 | prep 失敗 → abort(prep_failed) | 換 runner 重試；斷線 >~40s 耗盡 attempts → JE（可見），admin rejudge 救 | JE 或 Pending +一輪 |
| Poison submission | attempts 達 3 | 標 JE（INV5） | 收到 JE |
| Rejudge 撞進行中 job | currency 檢查 | 舊結果丟棄 + log；同 runner 並行合法（job_id keying） | 無感 |
| 死而復生 runner 送舊結果 | ownership → 409 / currency → 204+log | runner drop | 新結果為準 |
| Rolling restart 機隊 | drain abort 不計 attempts | 立即重派 | Pending 秒級 |
| Runner zombie（行程活、追蹤器騙人） | **不偵測**（N3） | executor 300s timeout 兜底 | 最差 ~5 分鐘 JE |

## 13. 參數

| 參數 | 值 |
|---|---|
| Heartbeat 間隔 / lease TTL | 15s / 30s |
| Poll 間隔 | 3s |
| Orphan 掃描時間閘 | 15s |
| MAX_ATTEMPTS | 3（claim+reclaim+計數性 abort 合計） |
| 身分 TTL | 7d |
| Presigned URL | 1hr |
| Runner 註冊 backoff | 1→2→4→8→16→30s |
| Complete/abort retry | ≤5 次 exponential backoff |

## 14. Infra

- Redis 開 AOF：`--appendonly yes --appendfsync everysec`（queue 的持久性依據）
- Sandbox service：entrypoint 改 `python main.py`；**restart policy `unless-stopped`**（fail-fast 重生依據）；無 HTTP port、無 healthcheck endpoint（liveness 由 backend 端 last-seen 呈現）
- `.secret/web.env`、`sandbox.env`：`RUNNER_REGISTRATION_TOKEN`（兩側同值）、`BACKEND_URL`

## 15. 交付計畫（G5 的落實）

### 15.1 原則
Small CLs / dark-launch（Keystone Interface + Parallel Change）：新碼以多個 100–400 行小 PR 登陸 main 但無人呼叫；keystone PR 完成切換並刪除舊路徑；部署仍一次到位。**完全重寫**——舊 branch `feat/pull-based-job-dispatch` 僅作為文件輸入，不搬碼，重寫完成後廢棄。

### 15.2 PR 切片（每片含測試、獨立綠燈）
**Back-End**
1. `dispatch/` 基礎：redis_keys、config、runner 註冊/驗證/GC（ZSET+TTL）
2. Job 生命週期：enqueue、claim（含 currency 銷毀）、renew、reclaim、時間閘掃描 + Lua
3. 落地與退還：complete（INV1/INV3/INV4）、abort（依原因計數）、JE 收斂
4. HTTP 層：blueprint 5 runner endpoints + `@require_runner_token` + schemas
5. Admin API：`GET /runners`
6. **Keystone**：`submit()`/`rejudge()` 切換 + 刪除全部舊 push 路徑 + 舊測試改寫

**Sandbox**
1. `runner/` → `executor/` 改名 + dispatcher job_id keying
2. `runner/` 協調層：client、registration、heartbeat（續租）
3. poller + result_sender + abort 流程
4. **Keystone**：`main.py` 入口、Flask/app.py 移除、Dockerfile CMD

**Meta-repo**：compose 整理（AOF、restart policy、env、submodule bump）一個 PR。

註：切片 1–5（backend）與 1–3（sandbox）皆為 dark（無呼叫者）；auth 相關切片（backend 1、4）實作與 review 需過安全視角檢查。

切片形狀是**刻意的分層切**而非垂直 tracer bullet：Lua 原子性審查集中在 job 生命週期兩片內（連貫審查優先於逐片可 demo），每片仍以 fakeredis 單元層獨立綠燈，HTTP 主 seam 的驗證集中於 HTTP 層切片與 keystone。

### 15.3 部署
挑無考試時段：merge keystone → bump submodules → `deploy.sh` → smoke test（提交一題、`docker kill sandbox` 驗證 45s 內 reclaim、`docker stop` 驗證 drain）→ 卡住的舊 submission 以 rejudge 救。Rollback：Mongo schema 未變，checkout 前版即可完全回退。

## 16. 測試策略

- Unit（fakeredis + lupa）：每支 Lua 的原子性與 race（雙 runner 同時 reclaim）、GC、時間閘、abort 計數矩陣（3 reasons × attempts 邊界）
- API（Flask test client）：6 endpoints happy/auth-fail/邊界（409/404/204-stale）
- Integration：mock runner 走完 register→claim→complete 全流程；failure injection（mid-process kill → reclaim、heartbeat 中斷、復活送舊結果 → 409、attempts 耗盡 → JE、drain 不計數）
- Runner side：協調層純單元測試（無 docker）；executor 沿用既有需 docker 的測試

## 17. 待驗證項（實作前確認）

1. **Runner testdata 快取失效**：rejudge 常因測資更新而發；`ensure_testdata` 的快取必須能感知測資變更，否則 rejudge 拿舊測資判題（既有系統就存在的隱患，重作時驗證並修復）。
2. **`process_result` 重算容忍性**：reclaim 重跑意味著同一 submission 的 `process_result`（含 `finish_judging` 的作業成績/統計更新）可能執行多次，須驗證為冪等或修正（ADR-0003 Consequences）。

## 18. v2 停車場

1. Heartbeat 回應夾帶取消提示（提早釋放非 current job 的容器）
2. Runner 端 zombie watchdog（補完 N3；lease hook 已備）
3. Queue depth 曝露（`/health` 或 metrics，供 ASG）
4. 長輪詢升級（若延遲敏感）
5. Frontend Runner 列表頁（取代最小 admin API 的人工查詢）
6. PG 遷移時清 `SubmissionConfig.sandbox_instances` 廢欄位
