# Runner 身分短暫化：memory-only 憑證 + 401 fail-fast + TTL 自動回收

Runner 憑證（`rn_id` + `rk_token`）只存記憶體，重啟即以新身分重新註冊；收到 401（連續兩次）直接 fail-fast 結束行程，交由 container restart policy 重生。Backend 端身分記錄設計為**可隨時從零重建的軟狀態**：`runners:registered` 為 ZSET（score = 最後 heartbeat 時間），`meta`/`token_hash` 帶 7 天 TTL 由 heartbeat 續期，死亡身分自動蒸發。Redis 被清空時全機隊 401 → fail-fast → 重註冊 → 自動收斂，零人工介入。

## Considered Options

- **無註冊、純共享密鑰**：更 stateless、少約百行程式碼，但整個機隊退化成單一信任域——無法個別踢除單台 runner（出事時全機隊換鑰重啟 vs 刪一個 Redis key），且 ownership 淪為自報。雲端 runner 走公網時是真實風險。
- **憑證落盤（穩定身分）**：log 連續性佳，但 runner 變有狀態，spot/ASG 場景每台要 volume，與「開機即用」目標相斥。
- **短暫身分但不回收（as-built）**：記錄無界累積，數月後 admin 列表全是死 runner。

## Consequences

`rn_id` 每次重啟改變；log 追蹤靠穩定的 `RUNNER_NAME`（記於 meta，admin API 一併顯示）。單台撤銷 = 刪除該 runner 的 token key，立即生效。
