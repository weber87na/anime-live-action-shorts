# AI 真人化 Shorts 技能

可自訂人物風格的 Codex skill：從角色候選圖、使用者選圖，到 AI 動態生成、轉場配樂與短影片驗收。

**每位角色至少 3 張候選圖；展示並詢問使用者，全部選齊且明確確認後，才生成影片。**

人物臉孔、年齡感、體格、服裝、背景與攝影風格由使用者設定。可使用 H3，也可接適合的其他生成後端；比例、時長、原動畫靜態小圖、標題片頭與音樂皆可調整。

## 安裝與使用

將此儲存庫放進 Codex 的技能目錄，資料夾名稱保留 `anime-live-action-shorts`。使用預設技能目錄的例子：

```bash
git clone https://github.com/weber87na/anime-live-action-shorts.git ~/.codex/skills/anime-live-action-shorts
```

若已設定 `CODEX_HOME`，則放在其 `skills` 子目錄。重新開啟對話後可使用：

```text
使用 $anime-live-action-shorts，把這組角色做成真人化短片。
人物風格由我設定，每個角色先給我至少 3 張不同候選圖，
等我選好並確認後再生成影片。
```

主流程見 [SKILL.md](SKILL.md)；[專案範本](assets/project.template.json) 的人物風格尚未設定，需先填寫。素材、選圖紀錄和成片應放在獨立工作目錄，避免混入此技能儲存庫。

## 執行環境

- 可用的圖片生成工具。此技能不包含模型權重或 API 金鑰。
- 使用者指定的影片生成後端。H3 路線使用環境另行安裝及登入的 `minimax-h3-colab`，不綁定個人 WSL 路徑。
- 可用剪輯工具；已有 `ffmpeg-skill` 時沿用其流程。
- Python 3.10+ 用於圖片確認檢查；檢查工具本身只依賴標準函式庫。

圖片確認工具會檢查候選數量、檔案內容、選取和確認指紋；它不會呼叫生成服務，也不能驗證人類是否真的提供確認。執行代理必須忠實記錄對話，並在每次提交生成之前執行檢查。

## 開發檢查

```bash
python -m unittest discover -s tests -v
```

本儲存庫僅包含技能、範本、工具與測試，不附實際作品素材、音樂、人物照片或生成影片。
