# c-sandbox 現行行為盤點（功能對等檢核表）

> Wayfinder ticket: [#74 Research: c-sandbox 現行為盤點 → 功能對等檢核表](https://github.com/Normal-OJ/Normal-OJ/issues/74)（map [#72](https://github.com/Normal-OJ/Normal-OJ/issues/72)）
> 依據版本（2026-07-14）：C-Sandbox `master@a2b962e`、Sandbox `5cdc907`、Back-End `8e78c34`。
> 用途：isolate 取代 c-sandbox 時的 parity 依據，餵給 [#78 executor 介面與結果語義對映](https://github.com/Normal-OJ/Normal-OJ/issues/78) 與 [#79 spec](https://github.com/Normal-OJ/Normal-OJ/issues/79)。

## 0. 執行模型總覽

每個 testcase 開一個 Docker container（`noj-c-cpp` 或 `noj-py3`），container 內以 **root** 執行 `sandbox` binary；binary `fork()` 後：

- **parent**：`wait4()` 收 `rusage`＋一條 watcher thread 在 wall-clock `time_limit + 300ms` 時 `SIGKILL`，結束後把 4 行結果寫進 result file。
- **child**：`setrlimit()` → stdio 重導 →（僅執行、非編譯時）`setegid(1450)`/`setuid(1450)` → 載入 seccomp → `execvp()`。

呼叫列（`Sandbox/runner/sandbox.py:53-70`，對應 `sandbox.c:33-58` 的 11 個參數）：

```
sandbox {lang_id} {compile} {stdin} /result/stdout /result/stderr \
        {time_limit_ms} {mem_limit_KB} 1 1073741824 10 /result/result
```

Container 設定（`runner/sandbox.py:71-101`）：`/src`（原始碼目錄，**rw**）、`/testdata/in`（測資輸入，ro；無輸入時 stdin 給 `/dev/null`）、`working_dir=/src`、`network_disabled=True`、**Docker 層無任何資源限制**。`client.wait` timeout = `5 * time_limit // 1000` 秒，逾時→ JE。

## 1. Status 清單與觸發條件

### Binary 層（result file 第 1 行，`sandbox.c:135-175`）

| Status | 觸發條件 |
|---|---|
| `Exited Normally` | 正常 exit、exit code 0、未超時、`ru_maxrss ≤ memory_limit` |
| `TLE` | watcher 已 kill（wall > t+300ms）、或 `ru_utime > time_limit`、或（signaled 時）`SIGXCPU` |
| `MLE` | `ru_maxrss > memory_limit`（事後比對，於 TLE 檢查之後） |
| `RE` | exit code ≠ 0、或被其他 signal 終止（含 seccomp `SCMP_ACT_KILL` 的 SIGSYS）、或 `wait4()` 失敗（此時寫 `RE\nwait4() = -1\n0\n0`） |
| `OLE` | signaled 且 `SIGXFSZ`（RLIMIT_FSIZE 超限） |

判定優先序——exited 路徑：`TLE > MLE > RE > Exited Normally`；signaled 路徑：`TLE > OLE > MLE > RE`。

### Service 層（Sandbox Python 產生，binary 不會出這些）

| Status | 觸發條件 |
|---|---|
| `AC` / `WA` | status ∉ {TLE, MLE, RE, OLE} 時，stdout 與期望輸出做 strip 比對（`runner/submission.py:70-86`）：每行 `rstrip()`＋去掉檔尾空行，相等→AC，否則 WA |
| `CE` | compile job 的 binary status ≠ `Exited Normally`（**含 compile 超時/MLE/RE 都折成 CE**，`runner/submission.py:49-52`） |
| `JE` | docker wait 逾時或例外、result 檔取回/解析失敗（`runner/sandbox.py:107-126`、`runner/submission.py:47-48,66-67`） |

### Back-End 層（`mongo/submission.py:135-145`）

字串 → 整數：`AC=0, WA=1, CE=2, TLE=3, MLE=4, RE=5, JE=6, OLE=7`；另有 `-1` pending、`-2` 未送出。聚合：case→task、task→submission 都取 `max()`（數字大者蓋過，等同上表順序的「嚴重度」）；score = task 全 AC 才得 `taskScore`，submission 為總和。

### ExitMsg 的用途與消費者

result file 第 2 行，格式如 `WIFEXITED - WEXITSTATUS() = 0`、`WEXITSTATUS() = %d, WTERMSIG() = %d (%s)`、`wait4() = -1`。消費者只有 Sandbox 內部的 `Result.ExitMsg`（`runner/sandbox.py:135`）與 C-Sandbox e2e 測試；**dispatcher 的 complete callback 沒有這個欄位**（`dispatcher/dispatcher.py:338-345`），Back-End 從未看到。→ parity 上視為 debug-only，受測程式的真實 exit code / signal **不會**上傳。

## 2. 限制項與單位/語義

| 參數 | 值與來源 | 單位 | 執行機制（`sandbox.c:200-237`） |
|---|---|---|---|
| `time_limit` | problem meta 的 `task.timeLimit`（Sandbox 自己向 Back-End `GET /problem/<id>/meta` 取得） | ms | `RLIMIT_CPU` soft=`t/1000+1`（`t%1000>800` 再 +1）、hard=soft+1（秒，user+sys）；watcher wall-clock `t+300ms` SIGKILL；**TLE 判定只看 `ru_utime`（user time）** |
| `memory_limit` | `task.memoryLimit` | KB | `RLIMIT_AS` soft=`2×KB×1024` bytes、hard=soft+1024；MLE 為事後 `ru_maxrss > KB` 比對 |
| `large_stack` | Sandbox 恆傳 `1` | bool | `RLIMIT_STACK` 設成與 AS 相同（即 2× mem limit） |
| `output_limit` | 硬編碼 `1073741824`（`runner/sandbox.py:66`） | bytes（1 GB） | `RLIMIT_FSIZE` → 超限收 `SIGXFSZ` → OLE |
| `process_limit` | 硬編碼 `10`（`runner/sandbox.py:67`） | 個 | `RLIMIT_NPROC` soft=hard=`limit+1`＝11 |
| compile 專用 | time=`20000ms`、mem=`1048576KB`（`runner/submission.py:40-41`） | — | 同上機制 |

各 rlimit 只在參數非 0 時設定。回報值：`Duration` = `ru_utime` 換算 ms（watcher kill 時改回報 `t+300`）；`MemUsage` = `ru_maxrss`（KB）。

## 3. seccomp 政策與 lang_id 的作用

`lang_id` 在 binary 內做兩件事（`sandbox.c:65-95,289-296`）：選 compile/execute argv（`lang.h`），以及選 seccomp 政策。**compile job 完全不載 seccomp、也不 setuid（以 root 跑）**。

### c11 / cpp17 執行（`rule.h c_cpp_rules`，`allow_write_file=0`）

預設 `SCMP_ACT_KILL` 的**白名單**：

- `execve` 只允許第一參數 == target 字串的**指標值**（依賴 `execvp` 傳同一指標，脆弱但有效）。
- 白名單 25 個 syscalls：`read fstat mmap mprotect munmap uname arch_prctl brk access exit_group close readlink sysinfo write writev lseek clock_gettime fcntl pread64 faccessat newfstatat set_tid_address set_robust_list rseq prlimit64`。
- `open`/`openat` 僅允許非 `O_WRONLY|O_RDWR`（唯讀開檔）。
- 沒有 `clone` → 無法建 thread/子行程。

**維護痛點即在此**：glibc 演進會用新 syscall（`rseq`、`prlimit64` 就是後來補的），每次 toolchain/基底 image 升級都可能要擴白名單，否則好程式被 SIGSYS 殺掉判 RE。

### python3 執行（`rule.h general_rules`）

預設 `SCMP_ACT_ALLOW` 的**黑名單**：KILL `execve`（target 以外）、`clone`、`fork`、`vfork`、`kill`，以及 `open`/`openat` 帶 W/RW flag。→ 禁 thread/subprocess/寫檔（僅擋 open 路徑）。防護強度遠弱於 c/c++ 白名單。`python3_rules()` 是空殼、未使用。

## 4. compile 流程

1. 只有 C/CPP 需要編譯（`dispatcher/dispatcher.py:60-61`）。`handle()` 先排 `Compile` job；`Execute` job 若 compile 尚未完成就 requeue（`dispatcher.py:202-205`）。
2. compile 也是開一個 `noj-c-cpp` container 跑 `sandbox {lang_id} 1 ...`，limits 固定 20s / 1GB；binary 內以 root、無 seccomp 執行 `lang.h` 的編譯命令：
   - c11：`sh -c "gcc -DONLINE_JUDGE -O2 -w -fmax-errors=3 -std=c11 *.c -lm -o main"`（收**所有** `*.c`）
   - cpp17：`g++ -DONLINE_JUDGE -O2 -w -fmax-errors=3 -std=c++17 main.cpp -lm -o main`（**只收 `main.cpp`**）
3. 產物 `./main` 寫回 `/src`（host bind mount），後續每個 testcase container 重掛同一 `/src` 執行 `./main`；python 直接 `/usr/bin/python3 main.py`。
4. 判定：`Exited Normally` → 內部記 AC；**其他一律 CE**。CE 時跳過所有 execute，每個 case 直接回報 compile 結果（gcc 的 stderr 會隨 case 上傳，`dispatcher.py:287-306`）。

## 5. result file 格式與資料流

Result file 共 4 行：`Status\nExitMsg\nDuration\nMemUsage`。Sandbox 以 `docker get_archive('/result')` 取回 tar，解出 `result`/`stdout`/`stderr` 三檔（`errors='ignore'`），`result.split('\n')` 按行取值（`runner/sandbox.py:117-138`）。

Callback（`dispatcher.py:319-403`）：case key 為 `TTCC` 字串（task 2 位＋case 2 位），全部完成後 `PUT {BACKend}/submission/<id>/complete`，payload：

```json
{ "tasks": [[{ "stdout": "...", "stderr": "...", "exitCode": <DockerExitCode>,
               "execTime": <ms>, "memoryUsage": <KB>, "status": "AC" }, ...], ...],
  "token": "<SANDBOX_TOKEN>" }
```

注意 `exitCode` 是 **container 的離開碼**（`DockerExitCode`），不是受測程式的 exit code（那個只在 ExitMsg 文字裡、不上傳）。

## 6. Image 部署與 uid 1450 約定

- `build.sh` 從 `https://github.com/Normal-OJ/C-Sandbox/releases/latest/download/sandbox` 下載 binary（**無版本釘選**），`COPY sandbox /usr/bin/` 進兩個 image。
- `noj-c-cpp`：`ubuntu:22.04` + `libseccomp-dev` + `gcc`/`g++`（apt 浮動版本，22.04 ≈ gcc 11）。`noj-py3`：`ubuntu:22.04` + `seccomp` + `python3`（≈ 3.10）。
- 兩個 Dockerfile 都 `useradd sandbox -u 1450` 並 `mkdir /result`；**未設 `USER`**，container 以 root 啟動（binary 開頭檢查 `getuid()==0`），執行受測程式前才降到 uid/gid 1450（寫死於 `sandbox.c:18-19`）。
- `/result/stdout`、`/result/stderr` 由 binary 以 mode `0644`（`S_IRUSR|S_IWUSR|S_IRGRP|S_IROTH`）建立。
- C-Sandbox 自身建置：`gcc -o sandbox sandbox.c -lpthread -lseccomp -Wall`（repo `makefile`，建置環境 `ubuntu:22.04`）。

## 7. Quirks／parity 決策點（#78 的輸入）

1. **TLE 只算 user time**：`ru_utime > t` 才 TLE；syscall-heavy（sys time 高）的程式靠 wall-clock watcher（t+300ms）兜底。isolate 的 time/wall-time/extra-time 語義不同，是判分漂移主要來源之一。
2. **watcher kill 時 Duration 回報 `t+300`**，不是實際用量。
3. **MLE 是事後比對**：硬限制 `RLIMIT_AS = 2×`，峰值落在 1×–2× 之間會「跑完才判 MLE」；>2× 則 malloc/mmap 失敗，結局由程式行為決定（常成 RE）。isolate 的 cgroup 記憶體限制語義不同。
4. **AC/WA 比對容忍**每行尾端空白與檔尾空行。
5. **多檔支援不一致**：c 編譯收 `*.c`、cpp 只收 `main.cpp`、python 只跑 `main.py`。
6. `RLIMIT_NPROC` 是 per-uid 全系統計數，平行 container 共用 uid 1450 理論上互相干擾；實務上 fork/clone 都被 seccomp 擋住，幾乎不觸發。
7. compile 以 root、無 seccomp 執行（僅靠 `network_disabled` 與 container 隔離）。
8. `client.wait` timeout = `5*t//1000` 秒：`t<200ms` 會得 0（行為存疑，未實測；現行題目 limit 多 ≥1000ms）。
9. dispatcher 有 300s submission timeout（`dispatcher.py:57,74-78`）：逾時的 job 被丟棄後 **callback 永不發生**，Back-End 端 submission 永遠 pending。
10. 版本皆不釘選：sandbox binary 抓 `releases/latest`，gcc/g++/python3 隨 `ubuntu:22.04` apt 浮動。
11. `SubmissionRunner` 的 `special_judge` 參數存在但未使用；Back-End dispatch 的 `checker` 欄位為硬編碼。
12. Back-End 另有 `language=3`（handwritten），不在 Sandbox 的 `Language` enum（0–2）內，不進 sandbox 流程。
13. `SubmissionRunner.__init__` 的 `time_limit` 註解寫 `# sec.`（`runner/submission.py:12`）但實際單位是 ms——讀碼時勿被誤導。
