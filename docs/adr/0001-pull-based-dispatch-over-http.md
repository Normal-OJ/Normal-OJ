# 判題派工採用 Pull over HTTP

判題 dispatch 從「Backend push 給 Sandbox」改為「Runner 出站連線 Backend HTTPS API 拉取 Job」。動機：submission 卡死 Pending 的三個破口（派送無 timeout/retry、sandbox in-memory 狀態蒸發、callback 單次嘗試）需要可靠交付機制，且運維目標是「考試前臨時開雲端 runner、考後關機」。Pull 讓 runner 不需可被定址（NAT/spot instance 直接可用）、backpressure 內建（有空才拉）、認證曝露面單向（只有 backend 開 endpoint）。

## Considered Options

- **Push + timeout/retry/sweeper**：機制較少，但 runner 需可定址且加機器要改設定，與動態擴增目標相斥；防重複判題的 lease 等價物照樣要寫。
- **Runner 直連 Redis/broker（含 Redis Streams consumer）**：省自製 queue 碼，但雲端 runner 意味著 Redis 曝露公網，憑證粒度與撤銷能力不足。
- **Celery + Redis**：Redis broker 的 worker 死亡重派靠 `visibility_timeout`，必須大於最長判題（300s）→ runner 斷電後 submission 卡 10–15 分鐘，比 30s heartbeat lease 差一個量級，框架語意無法補救。
- **Celery + RabbitMQ**：死亡偵測即時，但為判題引入第七個 infra 元件；容量模型與 Sandbox 內部容器池錯位。
- **反向連線 push（WebSocket）**：需 gunicorn 改 gevent/async，為 OJ 無感的 3 秒延遲付出部署模型手術。

## Consequences

判題 dispatch 明確**不**擴展為通用 task queue；未來寄信/MOSS 等背景工作另行採用 in-stack Celery/RQ + 現有 Redis（worker 與 broker 同內網，無曝露問題），兩套機制共存、各司其職。
