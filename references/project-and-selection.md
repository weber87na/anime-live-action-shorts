# 專案設定與選圖紀錄

`assets/project.template.json` 是可填寫的起點；人物風格欄位刻意留空，須由當次使用者設定。JSON 使用 UTF-8，所有相對路徑以 `project.json` 所在目錄解析。工具需要 Python 3.10+，只使用標準函式庫。

## 欄位責任

| 欄位 | 用途 |
| --- | --- |
| `project_id` | 此專案的穩定識別值 |
| `style` | 使用者共用人物風格，保留原意，不填固定人物或演員預設 |
| `characters[].id/name` | 角色／形態的穩定 ID 與顯示名稱；同人不同形態用不同 ID |
| `characters[].canon` | 已查證原作資料，含來源；與呈現設定分開 |
| `characters[].appearance` | 對共用風格的角色覆寫，含年齡感、體格、髮型與服裝等 |
| `characters[].candidates` | 至少 3 張候選圖的 `id`、`path`、實際 `sha256`，以及可選 `prompt_path` |
| `characters[].selected_candidate_id` | 使用者選取的候選 ID，尚未選擇時為 `null` |
| `selection_confirmation` | `confirm` 命令寫入的使用者確認紀錄，初始為 `null` |
| `video / audio / layout` | 剪輯設定；範本的 9:16、30fps 等只是可修改的初始技術值 |
| `generation` | 選定的生成後端、品質、工作環境設定 |
| `sources` | 原圖、音樂、原版片頭等的來源、使用區間與本地位置 |

外貌敏感的設定必須放在 `style` 或 `appearance`，不要藏在未受選圖指紋保護的剪輯欄位。圖片提示詞可放在專案 `prompts/`；原圖可放 `candidates/<character-id>/`。範本預留的空候選陣列不是可執行的已核准專案。

## 建立選圖表

每位角色有一張帶候選編號的聯絡表和至少 3 個原圖連結；編號須與 JSON 一致。展示後詢問選擇，例如：

> 已展示每位角色的 3 張候選圖。請指定每位要使用的編號，例如「角色 A 用 a-02、角色 B 用 b-03，確認用這組製作影片」；也可以告訴我要重畫哪位。

使用者只選其中幾位時，保留選擇並詢問剩餘角色，不推論空白值。圖片或外貌變更後，原確認只能作歷史紀錄，不能直接沿用為新確認。

SHA-256 可使用 `selection_gate.py sha256 <image>` 或 Python `hashlib` 計算，以小寫十六進位存入 JSON；PowerShell 可用 `(Get-FileHash -Algorithm SHA256 <image>).Hash.ToLowerInvariant()`。每張需實際可讀且非空，候選 ID、解析後路徑及圖片位元組雜湊均需不同。程式能擋相同位元組，**視覺上的實質差異仍需人工／視覺模型檢查**。

## 命令與失敗處理

先將選擇寫入 JSON；僅在對話已有使用者明確確認後，將該段原話另存 UTF-8 文字檔：

```text
python <skill>/scripts/selection_gate.py confirm <project.json> --message-file <user-confirmation.txt>
python <skill>/scripts/selection_gate.py check <project.json> --write-approved <approved-images.json>
```

`check` 成功時退出 0，失敗時退出 2，並以 JSON 列出原因。成功的核准對照表含絕對圖片路徑和 SHA-256，用它建立後端輸入；絕對路徑僅用於該次執行，搬動專案後重新執行檢查即可。

確認指紋涵蓋專案 ID、共用風格、每個角色的 ID／名稱／外貌、候選 ID／路徑／雜湊與選取 ID，並驗證所有候選的實際位元組。修改上述內容必須重新確認。只改音樂、時長、版型等不會作廢人像選擇。

檢查未通過時不得使用殘留的核准表；修正專案、補齊候選或取得新的真實確認後再檢查。工具不會聯絡生成服務，也不能證明使用者確實說過確認文字，這項責任由執行對話的代理承擔。
