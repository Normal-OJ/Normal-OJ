# 結果落地不變量：Job 唯有結果寫入 Mongo 後才從 Redis 消失

Job 從 Redis 消失的唯一途徑，是其最終結果（正常成績或 JE）已成功寫入 Mongo；標 JE 失敗（Mongo 暫時不可用）時 Job 留在原地，由下次 orphan 掃描自然重試。搭配 `completing` 狀態 + per-submission lock 保證「至多一個 complete 寫入成功」（防 lease 在慢寫入期間過期、新舊 runner 先後回報造成的並發雙寫——`process_result` 更新成績統計且無交易保護）。

## Considered Options

- **je_pending 旗標（as-built）**：Lua 在 attempts 耗盡時先移除 job、標 JE 失敗再插旗補救。保證相同，但旗標側通道（誰插、誰讀、何時消失）+ 續租特判讓 review 負擔倍增；不變量是同一教訓的結構化表達。
- **極簡（只查 ownership）**：接受極低機率的成績髒資料（無法自動復原）與永久 Pending（原罪復發）。

## Consequences

`process_result` 在任何方案下都必須容忍同一 submission 被完整重算（reclaim 重跑本來就存在）——列為共通需求驗證項。
