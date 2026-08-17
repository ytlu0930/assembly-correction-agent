Purpose: 依日期記錄專案變更、影響檔案與變更原因。

## 2026-08-17

- 啟用 Git LFS 管理 JPG/PNG，並將 raw data、實驗輸出與 references 納入可版本化範圍。
- V4 Gemini client 加入 120 秒 request timeout，避免單一 inventory batch 無限等待；Reference batch 2 待續跑。
- V4 加入 inventory batch checkpoint resume 與三次結構化回應重試；已完成批次不重跑。
- V4 inventory 改採每批 5 類 descriptor 的分批盤點，再由 Python 合併與驗證，避免單次逐顆輸出被截斷。
- V4 模型呼叫提高結構化輸出上限並拒絕截斷 JSON，保留無效原始回應供稽核。
- 新增 V4 instance-level inventory/matching schema、完整覆蓋驗證與 deterministic error classifier。
- 修正 Round 02 眼球數量真值：Current 5、Reference 4；實例對應為 3 matched、2 Current-only、1 Reference-only。
- Inventory-v3 重跑恢復兩顆多餘眼球並消除連桿互換誤報，但仍漏掉中央缺少眼球且有三項不受支持 claim，整體仍判定失敗。
- 新增 inventory-v3：Schema 強制逐一盤點完整 Part Catalog 的 Current／Reference 數量與 attachment anchors。
- 新增 correspondence-v2：完整重複零件實例對帳、相機左右防誤判與多錯誤類型完整性檢查。
- 完成 Round 02 盲診斷：正確找到兩顆多餘眼球，但漏掉中央缺少眼球並產生三項不受人工真值支持的 claim，整體判定失敗。
- 固化 Round 02 人工真值並新增不暴露標籤或人工框的六視角盲診斷實驗。
- 建立 Round 02 `wrong_part` 六視角人工標註包，供盲診斷前建立獨立 Ground Truth。
- 調整 `REMOVE` 箭頭方向，使其由目標零件朝遠離模型中心的外側指示移除方向。
- 產生 POC-01H front 視角的最終 `REMOVE` 成品圖，並讓 deterministic annotator 套用 EXIF 顯示方向後再繪製。
- 影響檔案：`src/assembly_agent/imaging/annotator.py`、`tests/test_annotator.py`、`outputs/poc01h/final_remove.png`。
- 原因：確保最終原圖標記與修正後的候選定位共用相同座標系。
- 建立可攜式 AI 專案規則入口與文件治理骨架。
- 將專案需求文件由根目錄歸位至 `docs/REQUIREMENTS.md`。
- 影響檔案：`CLAUDE.md`、`AGENTS.md`、`rules.md`、`README.md` 與 `docs/` 管理文件。
- 原因：建立跨 AI 工具一致的規則入口與集中式文件治理結構。
