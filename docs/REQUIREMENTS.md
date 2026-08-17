Purpose: 定義 Assembly Correction Agent 的產品目標、範圍、資料條件與驗收要求。

# Multimodal Assembly Correction Agent

## Greenfield Project Requirements & Codex Collaboration Specification --- V2

> 文件用途：本文件用於從零重建一個全新的「多模態積木組裝修正
> Agent」。本版本已融合實際 Model 03、Model 08 測試影像、組裝
> SOP、零件圖庫、拍攝規範，以及前期架構討論所得之修正。
>
> 主要協作方式：ChatGPT / Codex / VS Code。
>
> 核心目標：讓開發 Agent 能依本文件建立全新 Repository、整理資料、驗證
> Vision Model、完成定位、修正規劃與原圖標記，最終形成可操作、可驗證的
> Assembly Correction Guide。
>
> 本文件為新專案的 Project North Star。若舊文件、舊 Repository
> 或既有實作與本文件衝突，以本文件為準。

------------------------------------------------------------------------

# 1. 專案一句話定義

本專案不是只告訴使用者「積木裝錯了」的 AI，而是一個能夠：

> **比較使用者目前的積木組裝狀態與指定 Correct
> Model，辨識真正發生錯誤的零件與位置，規劃如何修正，並直接在使用者真實原始照片上逐步標示操作方式，再重新驗證是否已修回正確模型的多模態組裝修正
> Agent。**

最終使用者得到的不是單純分類、JSON、Bounding Box
或流程圖，而是一個可操作的 **Assembly Correction Guide**。

------------------------------------------------------------------------

# 2. Greenfield 原則

1.  不延續舊 Repository 架構。
2.  不要求相容舊 API、Schema、Prompt、UI 或模組切分。
3.  舊專案中的 Grounding DINO、Normalizer、Gradio、Schema、Prompt
    等僅作候選方案。
4.  所有模組都必須以「是否有助於從錯誤 Current State 修回 Correct
    State」重新評估。
5.  優先完成最短可行 End-to-End Correction Chain。
6.  AI 輸出盡可能結構化，不讓下游程式解析任意自然語言。
7.  低信心時正式輸出 `uncertain`，禁止強迫模型猜測。
8.  能 deterministic 的工作不交給 LLM。
9.  Assembly Photo 不得由生成式圖片模型重新生成或修改。
10. 所有正式 Evaluation 必須避免 Ground Truth Label Leakage。
11. Model、Prompt、Reference、輸入圖片與輸出結果皆需可追溯。
12. 在實驗證據不足前，不提前加入複雜 CV Stack。

------------------------------------------------------------------------

# 3. 已知資料條件

目前專案已具備以下資料來源：

-   Model 03 多步驟 Correct Assembly Images。
-   Model 03 真實錯誤案例。
-   Model 08 多步驟 Correct Assembly Images。
-   Model 08 真實錯誤案例。
-   Front / Back / Left / Right / Top / Bottom 等多視角影像。
-   Model 03 組裝 SOP。
-   Model 08 組裝 SOP。
-   獨立零件列表與零件照片庫。
-   既有拍攝規範。
-   錯誤案例包含 missing / extra / wrong / position 等類型；資料中另有
    `criticalerror` 標籤，其正式語意需由原標註者確認後再映射。

這代表本專案不是任意物件辨識問題，而可被收斂成：

> **指定 Model + 指定 Step + 已知零件集合 + 已知 Correct Reference 下的
> constrained multimodal assembly correction problem。**

------------------------------------------------------------------------

# 4. Project North Star Pipeline

``` text
User Assembly Request
        ↓
Input Validation & Image Normalization
        ↓
Reference Resolver
        ├── Correct Multi-view Images
        ├── SOP / Step Information
        ├── Part Catalog
        └── Expected State / Step Delta
        ↓
Evidence Package Builder
        ↓
Vision Difference Analysis
        ↓
Error Hypothesis
        ↓
Cross-view / Reference Verification
        ↓
Confirmed Error
        ↓
Part / Target Localization
        ↓
Correction Policy & Planner
        ↓
Python Original-Image Annotation
        ↓
Instruction Renderer
        ↓
Assembly Correction Guide
        ↓
User Performs Physical Correction
        ↓
New Real Photo
        ↓
Verification Against Correct Reference
        ↓
Correct / Continue Correction / Uncertain
```

------------------------------------------------------------------------

# 5. 核心研究問題

## 5.1 Error Detection

輸出：

``` text
correct
error
uncertain
```

`uncertain` 為正式狀態。

## 5.2 Error Type Identification

MVP Schema 支援：

``` text
missing_part
extra_part
wrong_part
position_error
orientation_error
composite_error
unknown_error
none
```

`criticalerror` 不直接假設等於
`composite_error`。在沒有正式標註定義前，應保留原 Dataset
Label，並可暫時排除於主要 MVP 指標之外。

## 5.3 Part-level Error Identification

這是核心 KPI。

系統不能只回答：

``` text
extra_part
```

而應盡可能回答：

``` text
extra_part
PIN_RED_SHORT
位於中間藍色三角結構旁的紅色直立短桿
```

Part Identification 應優先從已知 Part Catalog 選擇 canonical
`part_id`，避免自由創造名稱。

## 5.4 Structural Relation Identification

同一種零件可能在模型中出現多次，因此 Part Type 不足以唯一描述目標。

Target 應盡可能表示為：

``` text
Part Identity
+
Structural Relation
+
View-relative Location
```

例如：

``` json
{
  "part_id": "PIN_RED_SHORT",
  "relation": {
    "anchor_part_id": "PLATE_BLUE_TRIANGLE",
    "relative_position": "right_side",
    "orientation": "vertical"
  }
}
```

## 5.5 Localization

Localization 必須拆成兩類。

### A. Present-object Localization

回答：

> Current Image 中已存在、需要操作的零件在哪裡？

適用：

-   extra_part
-   wrong_part 的 actual part
-   position_error 的 source
-   orientation_error

輸出可包含：

``` text
bbox
point
region
```

### B. Target-placement Localization

回答：

> 正確零件應該被放在哪裡？

適用：

-   missing_part
-   wrong_part replacement
-   position_error destination

Missing Part 不存在於 Current Image，因此不得以「找 missing part
bbox」作為定位策略。

------------------------------------------------------------------------

# 6. Part Catalog

建立正式 canonical Part Vocabulary。

建議 Schema：

``` json
{
  "part_id": "PIN_RED_SHORT",
  "display_name": "紅色短桿",
  "family": "pin",
  "color": "red",
  "reference_images": [
    "..."
  ]
}
```

規則：

1.  Vision Model 優先從 Catalog 中選擇 `part_id`。
2.  不允許模型在已有 Catalog 可表示時任意創造新 Part Type。
3.  Part Catalog 為識別限制與輔助證據，不等同於 Ground Truth。
4.  Part thumbnail 可用於最終操作指引。
5.  Part Catalog 與 Ground Truth 必須分離。

------------------------------------------------------------------------

# 7. Part Type 與 Part Instance

正式 Domain Model 應區分：

## PartType

代表「這是哪一種零件」。

例如：

``` text
PIN_RED_SHORT
```

## PartInstance

代表「模型中的哪一顆」。

例如：

``` text
PIN_RED_SHORT
attached to the right side of PLATE_BLUE_TRIANGLE
vertical orientation
```

這個區分對多個同色同型零件、Position Error 與 Localization 非常重要。

------------------------------------------------------------------------

# 8. Assembly Reference Package

V1 的 `reference_image + expected_state` 升級為：

``` text
AssemblyReferencePackage
```

建議包含：

``` json
{
  "model_id": "model03",
  "step_id": "03",
  "correct_views": {
    "front": "...",
    "back": "...",
    "left": "...",
    "right": "...",
    "top": "...",
    "bottom": "..."
  },
  "sop_reference": {
    "source": "...",
    "step": 3
  },
  "relevant_parts": [
    "PIN_RED_SHORT"
  ],
  "expected_state": {},
  "step_delta": {}
}
```

Reference Retrieval 必須 deterministic。

LLM 不負責自由決定「哪一張是正確 Reference」。

------------------------------------------------------------------------

# 9. SOP 與 Assembly Step Delta

SOP 不只作展示用途，也可作 Vision Reasoning 的結構證據。

建議建立：

``` text
AssemblyStepDelta
```

表示：

``` text
Previous Correct State
+
Step Operation
=
Current Expected State
```

Schema 可逐步擴充：

``` json
{
  "from_step": "02",
  "to_step": "03",
  "added_parts": [],
  "removed_parts": [],
  "expected_relations": []
}
```

MVP 若無法完整人工結構化 SOP，可先保存 SOP Image / Step
Reference，不得假造不存在的結構化 Ground Truth。

------------------------------------------------------------------------

# 10. 使用者輸入規格

不強制使用者一次提供六張照片。

MVP 建議：

``` json
{
  "model_id": "model03",
  "step_id": "03",
  "primary_image": {
    "path": "...",
    "view": "front"
  },
  "supporting_images": []
}
```

其中：

-   `primary_image` 必要。
-   `supporting_images` optional。
-   測試資料已知 view 時直接使用 metadata。
-   真實 UI 初期可讓使用者選擇 View。
-   View Classifier 不是 MVP 必要條件。

如果單張圖片不足以可靠判斷：

``` text
uncertain
↓
request_additional_view
```

例如要求補拍 Left 或 Top。

------------------------------------------------------------------------

# 11. Canonical Views

正式支援：

``` text
front
back
left
right
top
bottom
```

Reference 與 Dataset 必須使用一致 View Vocabulary。

拍攝規範 V2 應明確定義各方向的基準，不再只使用「避免側拍」這類泛化描述。

------------------------------------------------------------------------

# 12. Input Image Normalization

進入 Vision 前至少執行：

``` text
format validation
EXIF orientation normalization
resolution validation
image ID assignment
immutable source preservation
```

原始照片不可覆寫。

Normalized copy 與 original source 必須可追溯。

------------------------------------------------------------------------

# 13. Evidence Package

Vision Model 不直接接觸整個 Repository。

由系統建立明確 Evidence Package，例如：

``` text
Primary Current Image
Optional Supporting Current Views
Matched Correct Reference View
Selected Supporting Correct Views
Relevant SOP Step
Relevant Part Catalog Entries
Expected State / Step Delta
```

目標是提供足夠證據，但避免無限制塞入所有圖片造成 context noise。

------------------------------------------------------------------------

# 14. Vision Model Strategy

第一優先驗證高能力多模態模型。

目前推薦以高能力 Gemini Pro 系列作主要
baseline，但模型名稱必須配置化，不可寫死於業務邏輯。

Vision Model 負責：

``` text
visual comparison
error hypothesis
part identification
structural relation
evidence extraction
initial localization attempt
```

不負責：

``` text
重畫 assembly photo
自由決定 correction policy
修改 ground truth
```

------------------------------------------------------------------------

# 15. Vision Analysis Contract V2

建議：

``` json
{
  "status": "correct | error | uncertain",
  "error_type": "missing_part | extra_part | wrong_part | position_error | orientation_error | composite_error | unknown_error | none",

  "actual_part": {
    "part_id": null,
    "description": null,
    "relation": null
  },

  "expected_part": {
    "part_id": null,
    "description": null,
    "relation": null
  },

  "current_location": {
    "region": null,
    "bbox": null,
    "point": null
  },

  "expected_location": {
    "region": null,
    "bbox": null,
    "point": null
  },

  "evidence": [
    {
      "source_id": null,
      "view": null,
      "supports_hypothesis": null,
      "note": null
    }
  ],

  "confidence": 0.0,
  "reason": ""
}
```

規則：

1.  `correct → error_type=none`。
2.  無法確認 Part 時使用 `null` / `uncertain`。
3.  `confidence` 只作 debug，不當成統計真實機率。
4.  `reason` 不作 downstream deterministic 判斷。
5.  Ground Truth 不得存在於 Model Context。
6.  Evidence 必須指出其來源影像 / reference。

------------------------------------------------------------------------

# 16. Error Hypothesis Verification

V1 的：

``` text
Vision
→ Error
→ Localization
```

改成：

``` text
Vision Comparison
→ Error Hypothesis
→ Evidence Verification
→ Confirmed Error
→ Localization
```

Cross-view Verification
的目的不是讓第二次模型重新自由猜一次，而是驗證既有 hypothesis
是否受到其他 evidence 支持。

例如：

``` text
Hypothesis:
extra PIN_RED_SHORT beside central triangular structure

Front → support
Left  → support
Top   → support
Correct references → no corresponding part
```

只有達到 Verification Policy 才進 Planner。

若證據互相矛盾：

``` text
uncertain
```

------------------------------------------------------------------------

# 17. Localization Strategy

採分層 fallback。

## Level 1 --- Native VLM Localization

先測 Vision Model 是否能直接產生可靠 bbox / point。

## Level 2 --- Grounding Model

只有當：

``` text
Part Identification 正確
但座標不可靠
```

才加入 external grounding。

## Level 3 --- Candidate Selection

多 Candidate 時根據：

``` text
part_id
structural relation
expected region
VLM hint
candidate geometry
reference relation
```

選擇。

## Level 4 --- Segmentation

只有 Bounding Box 無法滿足操作標記需求時才加入。

Segmentation 不是 MVP 前置條件。

------------------------------------------------------------------------

# 18. Coordinate Convention

同一 Pipeline 禁止混用座標格式。

若 Vision Provider 使用 normalized 0--1000，可在 provider adapter
層接受其原生格式，再統一轉換成 internal coordinate model。

Internal Schema 必須明確記錄：

``` text
coordinate_space
image_width
image_height
```

Annotation 前必須驗證：

``` text
x/y bounds
bbox order
non-zero area
source image dimensions
```

------------------------------------------------------------------------

# 19. Correction Planner

Planner 只接受已確認 Error。

核心 action sequence 採 deterministic policy：

## Missing Part

``` text
ADD
→ VERIFY
```

## Extra Part

``` text
REMOVE
→ VERIFY
```

## Wrong Part

``` text
REMOVE
→ ADD
→ VERIFY
```

## Position Error

``` text
MOVE
→ VERIFY
```

或必要時：

``` text
REMOVE
→ PLACE
→ VERIFY
```

## Orientation Error

``` text
ROTATE
→ VERIFY
```

## Composite Error

拆解成多個已確認 atomic errors，再依 dependency 排序。

MVP 若尚未可靠支援 composite planning，可回傳 partial /
unsupported，而不是自由生成複雜操作。

------------------------------------------------------------------------

# 20. Correction Action Schema

``` json
{
  "step_number": 1,
  "action": "REMOVE | ADD | MOVE | ROTATE | PLACE | REPLACE | VERIFY",
  "target_part": {},
  "source_location": null,
  "target_location": null,
  "instruction": "",
  "annotation": {
    "type": "box | arrow | point | highlight | rotation | none"
  },
  "verification": ""
}
```

每個 Step 只包含一個主要物理操作。

------------------------------------------------------------------------

# 21. Image Fidelity Contract

這是 V2 的硬性要求。

> **正式操作修正圖不得重新生成 Assembly Photo。**

規則：

1.  Current Assembly pixels 必須源自使用者原始照片。
2.  Correct Reference pixels 必須源自真實 Reference Dataset。
3.  Generative Image Model 不得修改 Assembly Photo。
4.  只允許 approved annotation overlays。
5.  原始圖片永遠不可覆寫。
6.  每張 output image 必須記錄 `source_image_id`。
7.  非 annotation mask 區域的 pixel 不應因 annotation pipeline 被改變。
8.  不得生成「假裝使用者已完成操作」的照片。
9.  修正後狀態必須由使用者真正操作後重新拍攝，才能作 Verification。
10. AI-generated illustration 只能作概念展示，不得當正式 Correction
    Evidence。

------------------------------------------------------------------------

# 22. Python Annotation Layer

Python 不負責理解圖片，只負責 deterministic rendering。

最低功能：

``` text
read image
copy image
draw bbox
draw point
draw arrow
draw curved arrow
draw rotation arrow
draw highlight
draw step badge
draw action label
save output
return metadata
```

建議另支援：

``` text
draw_part_thumbnail
draw_part_callout
draw_reference_crop
```

主要 library：

``` text
Pillow
OpenCV
```

可先選一套。

------------------------------------------------------------------------

# 23. Instruction Renderer

正式區分：

``` text
annotate_original_image()
```

與：

``` text
render_instruction_card()
```

`annotate_original_image()` 只處理真實照片 Overlay。

`render_instruction_card()` 負責組合：

``` text
annotated original image
step title
action
part thumbnail
instruction text
reference crop
verification status
```

原則：

> **Generate the instruction layout, never generate the assembly
> photograph.**

------------------------------------------------------------------------

# 24. 各錯誤類型的正式視覺策略

## Extra Part

使用：

``` text
Original Current Photo
+
bbox
+
REMOVE label
+
outward arrow
```

## Missing Part

不存在 current bbox。

使用：

``` text
Original Current Photo
+
target placement point / region
+
ADD HERE
+
part thumbnail
```

## Wrong Part

Step 1：

``` text
Current Photo + wrong-part bbox + REMOVE
```

Step 2：

``` text
Current Photo + expected target location + ADD
+
expected part thumbnail
```

## Position Error

``` text
source bbox
+
movement arrow
+
target point / region
```

## Orientation Error

``` text
target bbox
+
rotation arrow
```

## Verify

使用真實照片與真實 Correct Reference 比較，不生成修正後照片。

------------------------------------------------------------------------

# 25. Closed-loop Correction

正式 Agent 應支援：

``` text
Detect Error
↓
Generate One Correction Action
↓
User Physically Corrects Assembly
↓
User Uploads New Real Photo
↓
Re-analyze
↓
Correct?
├── Yes → Finish
├── No  → Next Correction
└── Uncertain → Request Better / Additional View
```

因此系統本質不是一次性「生成整份假想操作流程」，而是可逐步驗證的
Correction Loop。

MVP 可先完成單一 error → action → verify 的完整 loop。

------------------------------------------------------------------------

# 26. Final Assembly Correction Guide

最終至少包含：

``` text
Analysis Summary
Detected Error
Affected Part
Current / Correct Comparison
Correction Step
Annotated Original Image
Part Callout if needed
Verification Instruction
Final Status
```

例如 Extra Part：

``` text
Detected Error
Extra Part — PIN_RED_SHORT

Step 1 — REMOVE
[Original Error Photo + Python Overlay]

移除紅框中的紅色短桿。

完成後請重新拍攝同一視角。

Verification
[New Real Photo] vs [Correct Reference]

Result:
Correct / Continue / Uncertain
```

------------------------------------------------------------------------

# 27. Generative Image Model Policy

第一版不使用 Text-to-Image / Image Editing Model 生成正式修正照片。

原因：

``` text
part count drift
color drift
geometry drift
position drift
non-target modification
false completed-state visualization
```

生成式圖片只能用於：

``` text
UI concept
presentation mockup
future non-evidential illustration
```

不得作正式 Detection / Correction / Verification Evidence。

------------------------------------------------------------------------

# 28. Dataset Filename Contract & Manifest

現有照片檔名與資料夾結構已具備正式、可解析的命名規則，**不得為了新系統重新命名整批原始 Dataset**。

目前已確認的實際命名形式例如：

```text
model08_step05_extrapart-A01_bottom_01.jpg
model08_step05_missingpart-A01_back_01.jpg
model08_step02_correct-01_bottom_01.jpg
model08_step05_criticalerror-A01_left_01.jpg
model08_step05_positionerror-B01_left_01.jpg
model08_step05_wrongpart-A01_bottom_01.jpg
```

錯誤案例可依下列概念解析：

```text
{model}_{step}_{dataset_error_label}-{case_id}_{view}_{capture_id}.{ext}
```

Correct Case 則依既有格式解析，例如：

```text
{model}_{step}_correct-{case_id}_{view}_{capture_id}.{ext}
```

建立：

```text
src/assembly_agent/dataset/filename_parser.py
```

負責將現有 filename 解析成 metadata。

例如：

```text
model08_step05_positionerror-B01_left_01.jpg
```

解析為：

```json
{
  "model_id": "model08",
  "step_id": "step05",
  "state": "error",
  "dataset_error_label": "positionerror",
  "case_id": "B01",
  "view": "left",
  "capture_id": "01"
}
```

接著由 Parser 自動產生：

```text
data/dataset_manifest.json
```

Manifest 是原始 Dataset 的**衍生索引**，不是第二套人工維護命名系統。

規則：

1. 保留所有原始 filename。
2. 保留原始資料夾結構。
3. 不因 Manifest 而搬移或重新命名原始照片。
4. Metadata 優先由既有 Filename Convention 自動解析。
5. Parser 無法解析的 filename 必須報告 validation error，不得靜默猜測。
6. Manifest 至少保存：
   - image_id
   - model_id
   - step_id
   - state
   - dataset_error_label
   - case_id
   - view
   - capture_id
   - source_path
7. `image_id` 為系統內部識別碼，不代表實體檔案名稱。
8. Manifest 可重建，原始照片才是 source material。

## Multi-view Case Grouping

同一組：

```text
model_id
+
step_id
+
dataset_error_label / correct state
+
case_id
```

應自動 group 成同一 Assembly Case。

例如：

```text
model08_step05_extrapart-A01_front_01.jpg
model08_step05_extrapart-A01_back_01.jpg
model08_step05_extrapart-A01_left_01.jpg
model08_step05_extrapart-A01_right_01.jpg
model08_step05_extrapart-A01_top_01.jpg
model08_step05_extrapart-A01_bottom_01.jpg
```

應被視為同一個 Case 的不同 View，而不是六個互不相關案例。

Case-level representation 可為：

```json
{
  "case_key": "model08_step05_extrapart-A01",
  "model_id": "model08",
  "step_id": "step05",
  "dataset_error_label": "extrapart",
  "case_id": "A01",
  "views": {
    "front": "...",
    "back": "...",
    "left": "...",
    "right": "...",
    "top": "...",
    "bottom": "..."
  }
}
```

這個 Case Grouper 直接服務 Multi-view Analysis 與 Cross-view Verification。

## Dataset Label Preservation

原始 Dataset Label 保留原樣：

```text
extrapart
missingpart
wrongpart
positionerror
criticalerror
correct
```

Agent Domain Layer 可另外 mapping：

```text
extrapart      → extra_part
missingpart    → missing_part
wrongpart      → wrong_part
positionerror  → position_error
correct        → none
```

`criticalerror` 在原標註定義尚未確認前不得擅自 mapping 成 `composite_error`。


# 29. Ground Truth Separation

正式建立：

``` text
data/ground_truth/
```

Ground Truth 可包含：

``` text
image_id
is_error
error_type
actual_part_id
expected_part_id
expected_region
notes
```

未來若人工標註座標：

``` text
ground_truth_bbox
ground_truth_point
```

Ground Truth 僅供 Evaluator 使用。

Runtime Vision Context 不得讀取 Ground Truth Label。

------------------------------------------------------------------------

# 30. Anti-label-leakage Requirement

現有 Filename Convention 本身包含 Dataset Ground Truth，例如：

```text
model08_step05_missingpart-A01_back_01.jpg
```

其中 `missingpart` 已揭露 Error Type。

因此：

> **原始檔案不需要重新命名，但 label-bearing filename / path 不得成為 Vision Model 可見文字。**

Evaluation Runtime 應區分：

```text
Physical Source File
model08_step05_missingpart-A01_back_01.jpg

        ↓ internal lookup only

Model-facing Identity
eval_image_0042
```

規則：

1. 不重新命名實體 Dataset。
2. 不修改原始 filename。
3. Dataset / Evaluator 可知道真實 source path 與 label。
4. Vision Model Context 只接收圖片內容與 neutral model-facing ID。
5. Prompt 不得寫入 `missingpart`、`extrapart`、`wrongpart` 等 Ground Truth filename token。
6. Ground Truth label 不進 Prompt。
7. 若 API / SDK 自動暴露 filename，adapter 必須使用 neutral upload/display name 或其他不洩漏 label 的方式。
8. Logging 可保存真實 source path，但必須與 Model Context 分離。
9. `image_id` / `eval_image_xxxx` 僅是 Runtime Alias，不代表重新命名原始照片。
10. 違反此規則的 Evaluation Run 視為無效。


# 31. Reference Repository

建立 deterministic API，例如：

``` text
get_reference(model_id, step_id)
get_reference_view(model_id, step_id, view)
get_sop_reference(model_id, step_id)
get_relevant_parts(model_id, step_id)
```

不得由 LLM 自行搜尋資料夾或猜 Reference。

------------------------------------------------------------------------

# 32. 拍攝規範 V2 需求

原拍攝規範的背景、光線、解析度、完整可見等原則保留。

新增：

1.  Canonical View 定義。
2.  Front / Back / Left / Right / Top / Bottom 命名一致。
3.  拍攝方向基準固定。
4.  EXIF orientation normalization。
5.  同 Case 多視角盡量保持距離與尺度一致。
6.  修正後 Verification 優先要求與原 Primary View 相同視角。
7.  若系統要求 additional view，UI 必須明確告知需要哪個方向。
8.  不要求一般使用者預設一次拍攝六張。

------------------------------------------------------------------------

# 33. Evaluation Design V2

## Level 1 --- Detection

``` text
Correct / Error Accuracy
```

## Level 2 --- Error Type

``` text
Accuracy
Precision
Recall
F1
```

## Level 3 --- Part Identification

核心 KPI：

``` text
Canonical Part ID Accuracy
```

Error Type 對但 Part ID 錯，仍算 Part Identification Failure。

## Level 4 --- Structural Target

評估：

``` text
Part Type correct?
Part Instance / relation correct?
```

## Level 5 --- Localization

有人工 Ground Truth：

``` text
IoU
Point Distance
Target Hit Rate
```

無座標 Ground Truth：

``` text
Correct Target
Partially Correct
Wrong Target
```

## Level 6 --- Correction Plan

人工或規則檢查：

``` text
correct
complete
ordered
executable
leads toward reference state
```

## Level 7 --- Instruction Image

檢查：

``` text
target accuracy
text-image consistency
action clarity
non-target preservation
image fidelity
```

## Level 8 --- Closed-loop Success

``` text
Did the user-corrected new photo reach Correct State?
```

------------------------------------------------------------------------

# 34. Vision Experiments

## E01-A --- Single-view Baseline

Input：

``` text
Current Primary View
Matched Correct View
Relevant Part Catalog
```

測：

``` text
Error Detection
Error Type
Part ID
```

## E01-B --- Multi-reference

Input：

``` text
Current Primary View
+
Selected Correct Multi-view References
+
Part Catalog
+
Relevant SOP Evidence
```

比較 Part Identification 是否改善。

## E01-C --- Multi-current Verification

Input：

``` text
Primary Current View
+
Supporting Current View(s)
+
Correct References
+
Part Catalog
```

測 Cross-view Verification 是否降低錯誤 target。

## E02 --- Native Localization

只對 E01 已正確 Part Identification 的案例測 bbox / point。

## E03 --- Grounding Fallback

只有 E02 顯示：

``` text
Part correct
Localization weak
```

才啟動。

------------------------------------------------------------------------

# 35. Model Selection Principle

第一階段優先使用高能力 Vision Model建立 capability ceiling。

原則：

``` text
先證明能不能做到
再優化成本
```

模型名稱配置化：

``` text
VISION_PROVIDER
VISION_MODEL
VISION_TEMPERATURE
VISION_PROMPT_VERSION
```

未來可 benchmark 其他模型，但不得因品牌預設結果。

------------------------------------------------------------------------

# 36. Agent Orchestration V2

概念：

``` python
receive_request()
validate_input()
normalize_images()

reference_package = load_reference_package()

evidence = build_evidence_package()

analysis = run_vision_analysis(evidence)

if analysis.status == "correct":
    return correct_result

if analysis.status == "uncertain":
    return request_additional_evidence_or_uncertain()

verified = verify_error_hypothesis(analysis, evidence)

if not verified:
    return uncertainty_result()

localization = localize_action_target()

if localization.failed:
    return partial_or_uncertain()

plan = build_correction_plan()

step = select_next_action(plan)

annotated = annotate_original_image(step)

guide = render_instruction_card(step, annotated)

return guide
```

使用者完成操作後：

``` python
new_request = receive_verification_photo()
run_verification(new_request)
```

------------------------------------------------------------------------

# 37. Tool Boundaries

候選 Tool：

``` text
get_reference
analyze_assembly
verify_hypothesis
localize_part
annotate_image
compose_guide
```

但 deterministic function 不為了「Agent 化」而強制包成 Tool。

Tool 必須有清楚 I/O contract。

------------------------------------------------------------------------

# 38. Domain Objects V2

至少：

``` text
AssemblyRequest
AssemblyImage
AssemblyReferencePackage
AssemblyStepDelta

PartType
PartInstance

EvidencePackage
ErrorAnalysis
EvidenceRecord

LocalizationResult
CurrentLocation
ExpectedLocation

CorrectionAction
CorrectionPlan

AnnotatedImage
InstructionStep
AssemblyGuide

VerificationRequest
VerificationResult

RunRecord
```

正式 MVP 不應讓模組任意互傳無 schema dict。

------------------------------------------------------------------------

# 39. Error Handling Contract

至少：

``` text
INVALID_INPUT
IMAGE_NORMALIZATION_FAILED
REFERENCE_NOT_FOUND
PART_CATALOG_NOT_FOUND
VISION_FAILED
VISION_UNCERTAIN
HYPOTHESIS_NOT_VERIFIED
LOCALIZATION_FAILED
CORRECTION_FAILED
ANNOTATION_FAILED
IMAGE_FIDELITY_FAILED
GUIDE_FAILED
VERIFICATION_FAILED
```

低信心不等於 crash。

------------------------------------------------------------------------

# 40. Logging & Reproducibility

每次 Run 建立唯一：

``` text
run_id
```

最低記錄：

``` text
timestamp
input image IDs
model_id
step_id
views
references used
part catalog version
SOP reference
vision provider
vision model
model configuration
prompt version
vision output
verification evidence
localization output
correction plan
annotation metadata
output paths
final status
latency
errors
```

------------------------------------------------------------------------

# 41. Image Fidelity Test

Annotation Layer 必須可驗證：

``` text
Original Image
+
Annotation Mask
↓
Annotated Image
```

規則：

``` text
outside annotation mask:
pixel difference = 0
```

若實作中因 image encoding 造成全圖有不可避免的微小差異，應採 lossless
PNG working copy 或明確 tolerance，且必須記錄原因；不可因方便而取消
Fidelity Test。

------------------------------------------------------------------------

# 42. Testing Strategy

## Unit Tests

至少：

``` text
manifest schema
duplicate image ID
view enum
error type enum
part catalog lookup
reference retrieval
schema validation
correction policy
coordinate validation
annotation geometry
image fidelity
file output
```

## Integration Tests

至少：

``` text
Manifest → Reference Repository
Vision Output → Verification
Verified Error → Planner
Planner → Annotator
Annotator → Renderer
```

## End-to-End

至少使用現有真實案例：

``` text
1 correct case
1 missing case
1 extra case
1 wrong-part case
1 position case
```

若資料無可靠 ground truth，不自行偽造。

------------------------------------------------------------------------

# 43. MVP Acceptance Criteria

至少一個真實錯誤案例完成：

``` text
Real Original Photo
↓
Correct Error Detection
↓
Correct Canonical Part Identification
↓
Correct Target Localization
↓
Verified Error Hypothesis
↓
Correct Correction Action
↓
Python Annotation on Original Photo
↓
Human-readable Instruction
↓
User Performs Correction
↓
New Real Photo
↓
Verification Against Correct Reference
```

必要條件：

1.  真實現有照片。
2.  Part ID 正確。
3.  標記 target 正確。
4.  操作與 Ground Truth 一致。
5.  文字與圖一致。
6.  Assembly Photo 未被生成式模型修改。
7.  原始檔未被覆寫。
8.  中間輸出可追蹤。
9.  Ground Truth 未洩漏給模型。
10. Verification 使用新的真實照片或明確標示尚未驗證。

------------------------------------------------------------------------

# 44. Explicit Non-goals

MVP 不做：

``` text
robot arm control
AR guidance
real-time video
3D reconstruction
CAD registration
large-scale fine-tuning
universal LEGO recognition
arbitrary camera conditions
AI-regenerated assembly photos
automatic simulation of completed physical correction
full industrial production deployment
```

------------------------------------------------------------------------

# 45. Repository 建議結構 V2

``` text
assembly-correction-agent/
│
├── README.md
├── PROJECT_REQUIREMENTS.md
├── DATASET_RULES.md
├── EXPERIMENT_PLAN.md
├── DECISION_LOG.md
├── TODO.md
├── pyproject.toml
├── .env.example
│
├── src/
│   └── assembly_agent/
│       ├── agent.py
│       ├── config.py
│       │
│       ├── domain/
│       ├── dataset/
│       ├── reference/
│       ├── vision/
│       ├── verification/
│       ├── localization/
│       ├── correction/
│       ├── imaging/
│       ├── guide/
│       ├── evaluation/
│       └── logging/
│
├── data/
│   ├── dataset_manifest.json
│   ├── part_catalog.json
│   ├── references/
│   ├── sop/
│   ├── parts/
│   └── ground_truth/
│
├── outputs/
│   ├── experiments/
│   ├── annotations/
│   └── guides/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
└── scripts/
    ├── build_manifest.py
    ├── run_case.py
    ├── evaluate_vision.py
    └── evaluate_pipeline.py
```

------------------------------------------------------------------------

# 46. Development Order V2

## Phase 0A --- Dataset Audit & Manifest

完成：

``` text
scan existing data
manifest
neutral image IDs
view normalization
anti-label-leakage checks
```

不呼叫 AI。

## Phase 0B --- Part Catalog & Domain Models

完成：

``` text
canonical part IDs
part reference images
domain contracts
```

## Phase 0C --- Reference Repository

完成：

``` text
model + step → correct views / SOP / relevant parts
```

## Phase 0D --- Python Annotation POC

使用真實錯誤照片 + 人工正確 bbox：

``` text
Original Photo
+
REMOVE Overlay
```

驗證 Image Fidelity。

## Phase 1 --- Vision Capability Experiment

E01-A / B / C。

先回答：

> 高能力 Vision Model 能否找對真正錯誤 Part？

## Phase 1.5 --- Error Hypothesis Verification

建立 cross-view / reference verification。

## Phase 2 --- Localization

Native VLM first。

只有 Part Identification 正確但座標不穩，才加入 Grounding。

## Phase 3 --- Correction Planner

deterministic policy + structured actions。

## Phase 4 --- Instruction Renderer

組合：

``` text
annotated real photo
+
part thumbnail
+
instruction
+
reference evidence
```

## Phase 5 --- End-to-End Closed Loop

串接：

``` text
Detect
→ Verify
→ Localize
→ Correct
→ Annotate
→ User Action
→ Re-photo
→ Verify
```

## Phase 6 --- Evaluation

正式 Dataset Runner。

## Phase 7 --- UI

最後才做 UI。

------------------------------------------------------------------------

# 47. Codex Collaboration Rules V2

Codex 角色：

> Implementation Engineer + Code Reviewer + Test Engineer

不是產品需求決策者。

每次修改前先讀：

``` text
PROJECT_REQUIREMENTS.md
README.md
DATASET_RULES.md
current TODO
relevant source files
relevant tests
```

規則：

1.  先說明準備修改哪些檔案。
2.  優先最小修改範圍。
3.  不自行增加大型模型或 framework。
4.  不自行改 Domain Contract。
5.  每個新模組需有基本測試。
6.  External AI Test 與 deterministic unit test 分離。
7.  不用 mock 結果宣稱 Vision 已成功。
8.  Model name / parameters 配置化。
9.  API Key 不寫死。
10. Ground Truth 不進模型 Context。
11. 不將 label-bearing filename 暴露給模型。
12. 不使用生成式圖片模型修改 Assembly Photo。
13. 不生成「操作後完成照」代替真實 Verification。
14. Reference Retrieval deterministic。
15. 在 E01 結果前不自行加入 Grounding / Segmentation。
16. 若需求不確定，以 Project North Star 與 Image Fidelity Contract
    優先。

------------------------------------------------------------------------

# 48. Codex Task Format

``` markdown
## Goal
本次要完成什麼。

## Context
位於 Pipeline 哪一層。

## Inputs
輸入資料與型別。

## Outputs
輸出資料與型別。

## Constraints
禁止事項與必要規則。

## Files
預計新增 / 修改檔案。

## Acceptance Criteria
完成條件。

## Tests
必須執行的測試。
```

------------------------------------------------------------------------

# 49. 第一個正式 Codex Task

## Goal

建立 Filename Parser、Dataset Manifest Generator、Multi-view Case Grouper、Part Catalog、Reference Repository 與 Python Annotation POC。

## Existing Dataset Contract

現有照片已依固定格式命名，Codex 必須讓程式配合現有 Dataset，而不是要求 Dataset 配合程式。

禁止：

```text
bulk rename
moving original dataset
replacing original filenames with image_00001 style names
manual duplication of metadata already encoded in filenames
```

必須：

```text
parse existing filenames
validate filename format
preserve source paths
generate manifest automatically
group views by case
```

## Constraints

```text
No Gemini API
No Grounding Model
No UI
No generative image model
No ground-truth leakage
No original dataset renaming
```

## Required Output

```text
filename_parser.py
dataset manifest generator
dataset_manifest.json
multi-view case grouper
part_catalog.json
reference repository
core domain models
annotation module
image fidelity test
```

## Parser Acceptance Examples

至少能正確解析：

```text
model08_step05_extrapart-A01_bottom_01.jpg
model08_step05_missingpart-A01_back_01.jpg
model08_step02_correct-01_bottom_01.jpg
model08_step05_criticalerror-A01_left_01.jpg
model08_step05_positionerror-B01_left_01.jpg
model08_step05_wrongpart-A01_bottom_01.jpg
```

並正確區分：

```text
model
step
state
dataset error label
case
view
capture
```

## Annotation POC

使用真實 Model 03 Step 03 Extra Part Case。

先人工提供正確 bbox。

輸出：

```text
Original Error Photo
+
bbox around actual extra red rod
+
REMOVE
+
outward arrow
```

底圖必須是原始照片，不得重畫 Assembly。


# 50. 第二個正式 Codex Task

完成：

``` text
E01-A — Part-Level Vision Identification Baseline
```

固定：

``` text
Current Primary Image
Correct Matched Reference
Relevant Part Catalog
Structured Output Schema
```

記錄：

``` text
image_id
model
prompt_version
actual_error_type
predicted_error_type
actual_part_id
predicted_part_id
part_correct
latency
notes
```

Ground Truth 僅由 evaluator 在模型回傳後讀取。

------------------------------------------------------------------------

# 51. Architecture Decision Rules

遇到新技術選擇時依序問：

1.  它是否改善 Part Identification？
2.  它是否改善真正 target 的 Localization？
3.  它是否改善 Correction Action 正確性？
4.  它是否讓操作圖更清楚且不破壞原圖？
5.  它是否能被可靠 Evaluation？
6.  它是否只是增加架構複雜度？

如果主要答案是第 6 項，MVP 不加入。

------------------------------------------------------------------------

# 52. Definition of Done

不是：

``` text
程式可以執行
```

也不是：

``` text
AI 產生了一張看起來合理的修正示意圖
```

而是：

> **至少一個真實錯誤案例能從真實原始照片開始，由模型正確辨識錯誤零件，經過
> evidence verification、正確定位與 deterministic correction
> planning，再由 Python
> 只在原始照片上加入正確操作標記；使用者完成實體修正後，再以新的真實照片與
> Correct Reference 驗證是否修正成功。**

------------------------------------------------------------------------

# 53. 最終不可違反的五條規則

``` text
1. Correct Visual Understanding
2. Correct Canonical Part Identification
3. Correct Target Localization
4. Correct Correction Action
5. Original-Image Fidelity
```

任何新 Tool、Skill、Model、Prompt、UI 或 CV 技術，都只能服務這五件事。

------------------------------------------------------------------------

# 54. Project North Star

> **我們正在從零建立一個多模態積木組裝修正 Agent。系統根據指定 Model /
> Step 取得真實 Correct References、SOP 與 Part
> Catalog，將使用者目前的真實積木照片與正確狀態進行多模態比較，辨識真正發生錯誤的
> canonical part instance 與位置，透過其他視角與 Reference Evidence
> 驗證錯誤假設，再將差異轉成受 deterministic policy
> 約束的修正操作。所有正式操作圖片只能由 Python 在真實原始照片上加入
> Overlay，不得重新生成或修改積木本體。使用者完成實體操作後，系統以新的真實照片重新驗證，直到
> Current State 與 Correct Model
> 一致。所有技術選擇均以完成這條可驗證、可追溯的 End-to-End Correction
> Loop 為優先。**
