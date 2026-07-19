# Registration token 採啟動快照：更換共用密鑰需重啟，個別撤銷仍即時

`RUNNER_REGISTRATION_TOKEN` 作為 Back-End 集中部署設定（頂層 `config.py` 的 Settings）的一個欄位，**啟動時載入**，而非每次註冊請求時重讀環境變數。未設定 ⇒ 註冊停用（所有 register 一律 401，fail closed）。更換或撤銷這把全部署共用密鑰的生效方式是重啟 Back-End；個別 runner 的即時撤銷不受影響（刪 `token_hash` 即 401，ADR-0004）。

## Considered Options

- **每次驗證時重讀 env（live-read，slice 1 原設計）**：號稱密鑰移除立即生效，但容器化部署中改 `.secret/web.env` 本就要重建容器才會反映到行程環境——live-read 的「即時性」只在手動改運行中行程環境的罕見場景兌現，收益名不符實。代價卻是真實的：它成為全 codebase 唯一繞過集中 Settings 的設定讀取點，破壞「部署設定一律啟動時載入並驗證」的一致性。
- **Settings 欄位 + reload 通道（SIGHUP / admin endpoint）**：兼得快照一致性與即時更換，但為單一欄位引入 reload 機制是過度設計，多開一個複雜度與攻擊面。

## Consequences

共用註冊密鑰外洩時的處置＝改 `.secret` + 重啟 web（rolling restart，秒級；spec §12 已涵蓋 restart 期間的判題連續性）。已註冊 runner 持 `rk_` token，不受重啟影響。spec §7.1 措辭同步修正。dispatch 模組自此沒有自己的設定讀取：§13 協定常數住 `dispatch/params.py`，部署設定一律住頂層 `config.py`。
