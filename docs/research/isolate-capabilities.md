# isolate 能力與需求盤點（v2.6）

> Research 產出，對應 ticket [Research: isolate 能力與需求盤點 #73](https://github.com/Normal-OJ/Normal-OJ/issues/73)（map [#72](https://github.com/Normal-OJ/Normal-OJ/issues/72)）。
> 以 [ioi/isolate](https://github.com/ioi/isolate) 最新 release tag **v2.6**（2026-05-25）的第一手文件為準：man page（`isolate.1.txt`）、`README.md`、`NEWS`、`default.cf.in`、systemd units。

## TL;DR — 對本 map 的關鍵結論

- **isolate 2.x 只支援 cgroup v2**（cgroup v1 停在 1.10.1，2024 年起不再演進）。正式主機（Ubuntu 18.04 / kernel 4.15 / cgroup v1）無法使用，升級是硬前置（#75）。**記憶體用量回報需 kernel ≥ 5.19** → Ubuntu 22.04 GA kernel（5.15）不夠，建議直上 24.04（6.8）或 22.04＋HWE。
- **官方明言不建議在 container 內跑 isolate**：container manager 通常不會正確委派 cgroup，「要用的話你得自己來，而且大概得 privileged」。生態實務：Judge0 長年用 `--privileged` container；CMS 主流是主機直跑。這是「取代深度」決策（#77）的核心輸入。
- **syscall 模型與 c-sandbox 相反**：isolate 以 namespace 隔離為主，seccomp 只是小型 **denylist**（5 類跨 sandbox 洩漏管道），預設不限制一般 syscall。c-sandbox 的 glibc whitelist 維護痛點在 isolate 架構下不存在 — map 的動機成立。
- **打包**：官方 apt repo（Debian stable＋最近兩個 Ubuntu LTS，amd64）或 source build；上游無 GitHub release artifacts，只有 git tags。維護活躍（2026 年已釋出 2.3–2.6 四版，含安全修復 2.5）。

## 1. cgroup v2 需求

- isolate 2.0（2024-02）起**只支援 cgroup v2**；需要 cgroup v1 只能用 1.10.1。
- **systemd 主機**（建議路徑）：啟用 `isolate.service` — 跑一個極簡 daemon `isolate-cg-keeper`，掛在 `isolate.slice` 下、unit 設 `Delegate=true`，讓 systemd 把 cgroup 子樹正式委派給 isolate。設定檔 `cg_root = auto:/run/isolate/cgroup`（由 cg-keeper 寫入實際路徑）。官方 Debian/Ubuntu 套件會裝好 units 並處理啟用。
- **非 systemd**：自行決定 cgroupfs 掛載位置、把 `cg_root` 指過去，並確保 service manager 不會干擾 isolate 對 cgroup 的操作。
- kernel 需求：`cg-oom-killed` 回報需 ≥ 4.13；**記憶體用量回報需 ≥ 5.19**；建議完全關閉 swap（memory limit 管不到被 swap 出去的頁）。
- **non-cg 模式仍存在**（`--cg` 是 opt-in，`--init`/`--run`/`--cleanup` 都要帶）。犧牲：
  - 預設只允許單一 process/thread；開 `--processes` 後 **time/memory 限制對多 process 失效**（rlimit 是 per-process）。
  - 沒有 `cg-mem`（群組總記憶體）、沒有 OOM-kill 偵測。
  - 計時走 getrusage/rlimit；cg 模式下一律 cgroup 計時（2.0 已移除 `--cg-timing` 開關）。
  - 對 NOJ：c11/cpp17 單 process 理論上 non-cg 可用，但為了語義一致（python3、未來多 thread runtime），評測一律開 `--cg` 最單純。

## 2. 在 Docker container 內執行 vs 主機直跑

man page（INSTALLATION）原文立場：**不建議**在 container 內跑 —

1. container manager 通常不會正確委派 cgroup；
2. 評測機不該與其他 workload 共機（影響時間量測）；
3. 「若堅持要用 container，you are on your own，而且大概要 privileged」。

需求拆解（若走 container 路線）：

- isolate binary 是 **setuid root** 設計 — container 內須保留 root 與 setuid 語義。
- 需要**可寫的 cgroup v2 子樹**：正確做法是把委派好的 cgroup 子樹掛進 container（或 cgroup namespace＋`Delegate=`），偷懶做法是 `--privileged`（等於放棄 Docker 的 seccomp/AppArmor/capabilities 防線）。
- mount namespace 操作需要 `CAP_SYS_ADMIN`；isolate 要求 `/` 是 mount point（chroot 情境需先 `mount --bind` 自身，container 內通常天然成立）。
- 生態實務：[Judge0 作者在 ioi/isolate#35](https://github.com/ioi/isolate/issues/35) 回報長期以 `--privileged` container 運行（cgroup v1 時代還需 kernel cmdline 強制 v1）；[ioi/isolate#78](https://github.com/ioi/isolate/issues/78) 記錄了 container 內 `/sys/fs/cgroup` read-only 的委派問題；CMS 部署慣例是主機直跑。
- 對本 map：兩條路 — (a) isolate 主機直跑（Sandbox service 對 host 的關係要重新設計）；(b) sandbox container 加 privileged＋cgroup 委派。屬 #77 的決策範圍。

## 3. box 模型

- **生命週期**：`isolate --init`（印出 box 路徑，box 已存在則 reset）→ 填入執行檔與輸入 → `isolate --run -- prog args`（結束時 stderr 一行狀態、meta 檔落地）→ 從 box 撿輸出 → `isolate --cleanup`。
- **box-id**（`-b`，預設 0）：平行 sandbox 各需唯一 id；**每個 box-id 對應一個獨立的非特權 UID/GID**。UID 區段來源：v2.3+ 預設讀 `/etc/subuid`/`/etc/subgid` 中 `subid_user`（預設 `isolate` 使用者）的區段；或手動設 `first_uid`/`first_gid`/`num_boxes`（範例 1000）。**並行上限＝UID 區段大小（num_boxes）**，無其他內建上限。
- **Locking**（2.0+）：`--init` 後該 box 綁定呼叫者直到 `--cleanup`；同一 box 不允許平行 `--run`；第二個 instance 預設直接拒絕，`--wait` 可改為等待。
- **檔案系統**：box 內預設規則 — `/box`（工作目錄，rw）、`/bin` `/lib` `/lib64` `/usr`（ro bind）、`/proc`（只看得到自己 user 的 process）、`/tmp`（fresh，rw）、`/dev`（non-recursive bind）＋`/dev/shm`（fresh tmpfs；v2.6 修掉跨 box 共享 side channel）。`--dir` 規則可加掛（`rw`/`dev`/`noexec`/`tmp`/`fs`/`norec`/`maybe` 選項），`--no-default-dirs` 可全自訂。
- **CPU pinning**：設定檔 per-box `boxN.cpus` / `boxN.mems`（cpuset 語法）— 平行度與量測穩定性設計的素材。
- **Daemon 模式**：`restricted_init = 1`（只有 root 能建 box）＋ `--as-uid`/`--as-gid`（root 代其他使用者操作 box）。

## 4. meta 檔語義

`-M file` 輸出 `key:value` 文字檔。重點 key：

| key | 語義 |
|---|---|
| `status` | 兩字母碼：`RE`（非零 exit code）、`SG`（死於訊號）、`TO`（逾時）、`XX`（sandbox 內部錯誤）。**正常結束不寫 status/message** |
| `killed` | sandbox 主動終止（如逾時）時存在 |
| `exitcode` / `exitsig` | 正常結束的 exit code／致死訊號（擇一） |
| `time` | CPU 時間（秒，小數）。cg 模式取自 cgroup；non-cg 取 getrusage |
| `time-wall` | wall-clock 時間（2.2 起不受系統時鐘重設影響） |
| `max-rss` | 最大 RSS（KB） |
| `cg-mem` | cgroup 總記憶體（KB）。**注意：同一 box 連續多次 `--run` 會累計前次的 cache** |
| `cg-oom-killed` | 被 OOM killer 殺掉時存在（kernel ≥ 4.13） |
| `csw-voluntary` / `csw-forced` | context switch 計數 |
| `message` | 人讀訊息，不供機器判讀 |

- `--extra-time`：超過 `--time` 不立刻殺，多跑一段以回報真實用時 — 判 TLE 時能拿到實際時間。
- isolate 本身 exit code：0＝程式正常結束；1＝程式異常（RE/SG/TO）；其他＝isolate 內部錯誤。
- 對 #78（結果語義對映）：AC/TLE/MLE/RE 等 verdict 要由 executor 層從 `status`＋`killed`＋`cg-oom-killed`＋`time`/`time-wall` 對限制值推導（例如 MLE＝`cg-oom-killed` 或 `cg-mem` 達上限；TLE 需區分 CPU TO 與 wall TO）。

## 5. 限制項對照

| 限制 | 選項 | 超限行為 |
|---|---|---|
| CPU 時間 | `-t --time`（秒，小數） | 殺（經 extra-time 後）→ `TO` |
| Wall 時間 | `-w --wall-time` | 殺 → `TO`（建議設為 time 的數倍當保險） |
| 位址空間 | `-m --mem`（KB，**per process**） | 之後的 allocation 失敗（malloc 回 NULL） |
| 群組記憶體 | `--cg-mem`（KB，需 `--cg`） | alloc 失敗或 OOM kill（SIGSEGV）＋`cg-oom-killed` |
| Stack | `-k --stack`（KB） | SIGSEGV |
| 單檔大小 | `-f --fsize`（KB） | EFBIG＋SIGXFSZ |
| 磁碟配額 | `-q --quota`（blocks,inodes；`--init` 時給，需 fs quota 支援；2.2 起 tmpfs 可用） | EDQUOT |
| Core 檔 | `--core`（預設 0＝不產） | — |
| 開檔數 | `-n --open-files`（預設 **64**；0＝無限） | EMFILE |
| Process 數 | `-p --processes`（預設 **1**） | fork/clone 得 EAGAIN |
| 網路 | 預設新 network namespace（僅 loopback）；`--share-net` 開放 | — |
| 環境變數 | 預設全清（僅留 `LIBC_FATAL_STDERR_=1`）；`-E var`、`-E var=val`、`-e`（全繼承） | — |

**syscall 限制**：與 c-sandbox 的 whitelist 模式本質不同 — isolate 預設**不過濾一般 syscall**（隔離靠 namespace：socket 開得了但無處可連），只用 seccomp 擋 5 類跨 sandbox 資訊洩漏管道（設定檔 `syscall_flags` bitmask，預設全開）：keyctl（1）、AF_VSOCK（2）、跨 mount-namespace 的 file lock／lease／dnotify（4）、io_uring（8）、非原生架構如 i386-on-amd64（16）。glibc 更新不會產生 whitelist 維護工作。

## 6. 打包與維護狀態

- **Source build**：`make isolate` 只需 `pkg-config`＋`libcap-dev`＋`libseccomp-dev`；`isolate-cg-keeper` 另需 `libsystemd-dev`；man page 需 `a2x`（AsciiDoc）。
- **官方 apt repo**（`www.ucw.cz/isolate/debian/`）：Debian stable＋最近兩個 Ubuntu LTS，amd64（arm64 實驗性）。套件自帶 systemd units 並處理啟用；限 `isolate` group 成員使用。
- **無 GitHub Releases**，只有 git tags — 釘版即釘 tag 或 apt 版本。
- **release 節奏**：2.0（2024-02）→ 2.1（2025-06）→ 2.2（2025-09）→ 2.3（2026-04）→ 2.4（2026-04，加入 seccomp denylist）→ 2.5（2026-05，**安全修復**：GID 切換、maybe 選項 oracle、任意 fs mount）→ 2.6（2026-05，/dev/shm side channel）。維護者 Martin Mareš（CMS 生態主用），活躍且有安全修復流程。**釘版建議 ≥ 2.5**。
- 環境工具：`isolate --check-config`（驗設定檔）、`isolate-check-environment`（檢查 ASLR、cpufreq、THP、swap、不對稱核心等時間穩定性因子，可 `--execute` 直接套用）。
- Reproducibility 建議（man page）：關 ASLR、cpufreq governor 設 performance、關 turbo boost、box pin 到同質核心、THP 設 madvise/never、關 swap。

## 資料來源

- [ioi/isolate](https://github.com/ioi/isolate) v2.6：[isolate.1.txt](https://github.com/ioi/isolate/blob/v2.6/isolate.1.txt)、[README.md](https://github.com/ioi/isolate/blob/v2.6/README.md)、[NEWS](https://github.com/ioi/isolate/blob/v2.6/NEWS)、[default.cf.in](https://github.com/ioi/isolate/blob/v2.6/default.cf.in)、[systemd/](https://github.com/ioi/isolate/tree/v2.6/systemd)
- Container 實務：[ioi/isolate#35](https://github.com/ioi/isolate/issues/35)（Judge0 privileged 經驗）、[ioi/isolate#78](https://github.com/ioi/isolate/issues/78)（cgroup 委派問題）
- 設計論文：[Isolate's design](https://mj.ucw.cz/papers/isolate.pdf)、[grading system security](https://mj.ucw.cz/papers/secgrad.pdf)
