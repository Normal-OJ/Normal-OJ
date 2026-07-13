# Normal-OJ

大學程式評測系統（Online Judge）。使用者提交程式碼，系統在隔離環境中編譯、執行並評分。此 glossary 涵蓋跨 Back-End / Runner / 前端的共通語言。

## Language

### 判題派工（Job Dispatch）

**Runner**:
執行判題的服務節點。持 registration token 自我註冊取得身分，之後僅以出站連線向 Back-End 拉取工作。
_Avoid_: Sandbox（舊稱，僅指涉隔離執行技術時使用）、worker、judge machine

**Job**:
一次判題工作的派工單位，對應某個 submission 的一次評測嘗試；rejudge 會產生新的 Job。
_Avoid_: task（保留給 submission 內的測資群組）、work item

**Lease**:
Runner 對 Job 的有期限持有權。Runner 須在期限內持續續租，否則視同放棄。
_Avoid_: lock、claim（claim 指「取得 lease 的動作」，不是持有狀態本身）

**Orphan**:
Lease 已過期而未完成的 Job。Lease 過期是唯一判準；Runner 的死活不參與判定。
_Avoid_: stale job、dead job

**Reclaim**:
另一個 Runner 原子性地接管 Orphan、建立新 Lease 的行為。
_Avoid_: steal、takeover

**Registration token**:
全部署共用的預置密鑰，僅用於 Runner 首次註冊。
_Avoid_: shared secret、SANDBOX_TOKEN（舊稱）

**Runner token**:
註冊時核發給單一 Runner 的專屬憑證（`rk_` 前綴），用於其後所有 API 呼叫。
_Avoid_: API key、access token

**Submission**:
使用者的一次程式碼提交，判題結果的最終記錄單位。狀態由 Job 的完成回寫，Pending 表示尚無最終結果。
_Avoid_: entry、attempt

**Executor**:
Runner 行程內實際以隔離容器編譯、執行測資的元件層。
_Avoid_: sandbox runner、worker pool

**Drain**:
Runner 收到關機訊號後，退還未開始的 Job、等待進行中 Job 完成的收尾過程。Drain 造成的退還不視為 Job 的失敗。
_Avoid_: graceful shutdown（指整個行程層面時可用，指 Job 處置時用 Drain）
