Purpose: 維護專案待辦事項、優先序與可驗證的完成狀態。

## 待確認

- [ ] 使用者確認可攜式 AI 專案治理骨架。
- [x] 使用者在 Round 02 對照圖圈選並確認三個錯誤零件實例。
- [ ] 改善 correspondence-first 診斷，使 Round 02 找到中央缺少眼球並抑制不受支持的額外差異。
- [ ] 將同型零件盤點升級為逐 instance 的 attachment-level 一對一 matching；inventory-v3 僅改善部分誤報，整體仍失敗。
- [ ] V4 從 Reference inventory batch 2 checkpoint 繼續；Gemini 呼叫曾長時間無回應，現已加入 120 秒 timeout。

## 骨架確認後

- [ ] 依現有程式與需求補齊 `docs/ARCHITECTURE.md`。
- [ ] 整理目前 POC、測試結果與下一階段工作。
- [ ] 確認本 Agent 型專案是否需要建立專案內 `agent/` 或 `skills/` 內容。
