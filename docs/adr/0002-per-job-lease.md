# Per-job lease，lease 過期為 orphan 唯一判準

每個 Job 有自己的 `lease_deadline`，Runner 靠 heartbeat 夾帶 `active_job_ids` 逐一續租；lease 過期即為 Orphan（可被 reclaim）。**Runner 的死活不參與 orphan 判定**——`runner:alive` 僅供監控顯示。理由：只看 runner 死活的模型，在「runner 行程活著但處理某 job 的 worker thread 悄悄死掉」時該 job 永遠不會被接手——這正是原系統三大破口之一從側門復發；per-job lease 讓「工作遺失」而非「行程死亡」成為偵測單位，並為 v2 zombie watchdog 鋪好鉤子。

## Considered Options

- **Runner-alive only（原 spec v1）**：機制較少，但對 in-process 工作遺失完全無感知。
- **雙重判準（as-built：lease 過期 + runner 死活都查）**：兩個真相來源，review 難以說服自己不重不漏；重作時收斂為單一判準。
- **Redis Streams consumer group（XREADGROUP/XAUTOCLAIM）**：claim/過期轉移原生，但 stream entry 不可變——`attempts`（需跨 abort 累計）、`state=completing`、rejudge currency 都需要可變的 per-job 記錄，side hash 會全部長回來，簡化紅利被吃光；故採手寫 list/set/hash + Lua，每支 script 對應 spec 一條狀態轉移。
