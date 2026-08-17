# 可攜式 AI 專案安裝說明包（Portable AI Project Bootstrap Guide）

> 目的：讓任何 AI（不限 Claude Code／Codex，不假設有本工作區的腳本或路徑）在**任何 repo**中，
> 都能照本文件從零建立一套一致的「規則入口＋文件治理」結構。
> 本文件完全自足，不依賴 `init-project.sh` 或 `shared-ai/` 的任何其他檔案；純手動建檔即可完成。
> 若你剛好就在 techteam-dev 工作區內建立正式專案，請改用正本規範
> `shared-ai/repos/team-ai-standards/policies/project-structure.md` 與對應 playbook／腳本，本文件僅供對外分享或無腳本環境使用。

---

## 1. 核心原則

1. 規則入口固定為兩個薄檔案 → 都導向同一份 `rules.md`：
   - `CLAUDE.md`（給 Claude 類 AI）
   - `AGENTS.md`（給 Codex 類 AI）
2. `rules.md` 是這個專案**唯一的最高規範**，之後所有規則只寫在這裡一處，不重複散落。
3. 管理類文件（架構、任務、變更、決策、測試）一律放在 `docs/`，不要散落在專案根目錄。
4. 先建骨架、後填內容、再動手實作——不要一次跳到寫程式。

## 2. 標準目錄結構

```text
<project>/
├── CLAUDE.md            # 入口，只導向 rules.md，≤30 行
├── AGENTS.md             # 入口，只導向 rules.md，≤30 行
├── rules.md              # 唯一最高規範（文件地圖＋Skill 清單＋專案特有規則）
├── README.md             # 給人看的專案簡介
├── docs/                 # 管理文件（見第 3 節，至少 5 件）
├── agent/                 # 僅 agent 型專案：Agent Instruction 等指令產物
├── skills/                # 專案內的 AI Skill，一個 Skill 一個資料夾
├── scripts/               # 輔助腳本
├── tests/                 # 測試
├── references/            # 參考資料（規格、素材等）
├── .env.example
└── .gitignore
```

- `agent/`（資料夾，放指令產物）與入口檔 `AGENTS.md` 是兩回事，不要混用。
- 用不到的資料夾可以不建，但不要另創與上面同義的新名字（例如不要自己發明 `docs2/`、`plans/` 這種平行結構）。

## 3. `docs/` 必備文件（至少 5 件）

| 文件 | 用途一句話 | 何時更新 |
|---|---|---|
| `docs/ARCHITECTURE.md` | 目標與整體架構 | 架構一改就更新 |
| `docs/TODO.md` | 任務與進度清單 | 有新任務／進度變化就更新 |
| `docs/CHANGELOG.md` | 所有變更紀錄（日期／變更／影響檔案／原因） | 任何 change 都記一筆 |
| `docs/DECISION_LOG.md` | 重大決策紀錄（決策／原因／替代方案／日期／狀態） | 做重大決策就記一筆 |
| `docs/TEST_PLAN.md` | 測試策略與測試案例 | 新測試類型時更新 |

- 每份文件第一行寫一句 purpose，讓人（或 AI）一行就知道要不要繼續讀。
- 日期一律用絕對日期（YYYY-MM-DD），不要寫「今天／最近／上週」。
- 需要更多文件（例如 `REQUIREMENTS.md`、`DATA_MODEL.md`、`DEPLOYMENT.md`）依專案需要自行加，加了就寫進 `rules.md` 的文件地圖，不用先問過每種可能情境。

## 4. 依專案類型調整（由使用者決定細節，這裡只給大方向）

不用預先窮舉每種部門或情境，下面三種只是常見大類，實際取捨交給使用者：

- **一般專案**：上面第 2、3 節的骨架即可，`agent/` 可省略。
- **Agent 型專案**：保留 `agent/` 放 Agent Instruction／Prompt 等產物；`skills/` 通常會用到。
- **Fullstack 開發專案**：可能需要額外的 `docs/DATA_MODEL.md`、`docs/DEPLOYMENT.md`，以及前後端各自的程式目錄——這些細節等使用者確認後再建，不要自己先分好前後端資料夾。

## 5. 入口檔內容範本

`CLAUDE.md` 與 `AGENTS.md` 內容幾乎相同，只做導向，範例：

```markdown
# <project-name>

本檔為專案的 AI 入口，僅做導向，內容不在此展開。

所有規則、文件地圖、Skill 清單，請讀專案根目錄的 `rules.md`。
`rules.md` 是本專案唯一的最高規範，優先於任何其他共用規則。
```

## 6. `rules.md` 必備內容

1. 專案一句話定義（做什麼、給誰用）。
2. 執行優先序（例如：使用者當下指示 > 本檔 > 共用規則）。
3. 文件地圖表：本專案實際採用的 `docs/` 文件清單（含「何時必讀」欄）。
4. Skill 清單：本專案可用的 Skill 有哪些、放在哪。
5. 專案特有規則（如果有）：例如內容治理紅線、部署限制等。

## 7. 手動建立步驟（沒有腳本時）

1. 建立 `CLAUDE.md`、`AGENTS.md`（套用第 5 節範本）。
2. 建立空的 `rules.md`，先寫好第 6 節列的五個區塊骨架。
3. 建立 `docs/` 並放入第 3 節五份文件，各自只寫一行 purpose，內容留白等待補齊。
4. 依第 4 節判斷是否需要 `agent/`、`skills/` 等資料夾。
5. 停下來，交給使用者確認骨架是否正確，再開始填內容／實作。
6. 完成一輪工作後：`docs/CHANGELOG.md` 記一筆、有決策就記 `docs/DECISION_LOG.md`、有新任務就更新 `docs/TODO.md`。

## 8. 交付前自我檢查

- [ ] `CLAUDE.md`／`AGENTS.md` 都只做導向、沒超過 30 行？
- [ ] 規則只寫在 `rules.md` 一處，沒有到處重複？
- [ ] `docs/` 至少五件核心文件都在，且各自第一行有 purpose？
- [ ] 動到架構、有新任務、有變更、有決策 → 對應文件都更新了？
- [ ] 日期都是絕對日期？
- [ ] 有先停下讓使用者確認骨架，才進入實作？
