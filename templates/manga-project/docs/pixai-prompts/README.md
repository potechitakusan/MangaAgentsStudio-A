# PixAIのキャラクター・絵柄・背景・LoRAを編集して再生成する

このガイドは、**PixAI用の要求（`input/pixai/requests/`）ができている作品**で、キャラクターの外見・絵柄・背景・LoRAを変更し、画像を再生成してページを組み直すための手順書です。既存の作品フォルダで作業します。

> [!NOTE]
> 設定ファイルは３つに分かれています。
>
> | ファイル | 中身 | このガイドで編集するか |
> | --- | --- | --- |
> | `.env` | APIキー（`PIXAI_API_KEY` 等）・URLなどの共通設定 | しない |
> | `.env.novelai` | NovelAI用のプロンプト変数 | しない |
> | `.env.pixai` | **PixAI用のキャラクター・絵柄・背景・LoRAの変数と補助設定** | **する** |
>
> `.env.pixai.example` は見本で、編集しても反映されません。APIキーは `.env` のほか `.secrets/pixai.env` や環境変数にも置けます。

> [!IMPORTANT]
> PixAIの生成は**クレジットを使います**。残高を照会するAPIがないため、スクリプトは無料かどうかを判定できません。生成するときは、あなた自身が残高と範囲を確認し、AIエージェントへ「このモデル・設定で、このページを合計○枚まで、クレジットを消費して生成してよい」のように明示してください。準備や点検・生成の依頼だけではクレジット消費の許可になりません。

---

## 【最短手順】キャラクターの見た目だけを変更する

### 【初回のみ】Step 0. AIエージェントへ準備を依頼する

> 🤖 **AIへの依頼文例：**
> 「既存のPixAIの要求をもとに、キャラクター・絵柄・背景を `.env.pixai` から自分で編集できるように準備してください。キャラクターLoRAを使う場合はそのIDも変数にしてください。今回は画像の生成は行わず、準備だけお願いします。」

AIエージェントが変数名と値を提案し、確認のうえで `.env.pixai` へ書き込み、要求JSONを `${変数名}` の参照に置き換えます。

### Step 1. `.env.pixai` を書き換える

作品フォルダ直下の `.env.pixai` をテキストエディタで開き、該当する行の右側（`"` の中）を書き換えて保存します（UTF-8、改行なしの1行）。

```dotenv
PIXAI_CHAR_MIO="light brown short bob hair, yellow hairclip, yellow hoodie over navy blazer"
PIXAI_STYLE_MAIN="clean lineart, soft colors"
PIXAI_BACKGROUND_CLASSROOM="classroom, desks, windows, daylight"
PIXAI_LORA_MIO="1234567890123456789"
```

- `=` の左側の変数名は変えず、**右側の引用符の中だけ**を編集します。
- `PIXAI_LORA_` の値は、PixAIのLoRAのページのURL（`https://pixai.art/model/<モデルID>/<バージョンID>`）の**最後の数字（バージョンID）**だけです。重みは要求JSON側（`weight`、0〜1）で決めます。
- 強調は丸括弧 `(smile:1.2)` で書きます。角括弧・波括弧は使えません。
- 保存するだけで反映されます。

テキストファイルから反映したい場合は次のコマンドを使います（`.env.pixai` の他の行は変わりません）。

```powershell
python -X utf8 scripts/pixai_batch.py env-set PIXAI_CHAR_MIO --value-file input/pixai/prompts/mio.txt
python -X utf8 scripts/pixai_batch.py vars
```

### Step 2. 送信せずに確認する

```powershell
python -X utf8 scripts/pixai_batch.py generate --page 1 --batch-size 1
```

送信はせず、各コマのモデル・縦横比と出力の画素数・枚数・seed・使う変数と、プロンプトの警告を表示します。キーも読みません。この例は１コマ１枚で、５コマなら合計５枚です。既定の `--batch-size auto` では、候補があるコマの再生成が１コマ４枚になります。４枚ずつ選びたい場合は確認・実行の両方を `--batch-size 4` に揃え、表示された合計枚数のクレジット消費を許可してください。`--cost-note` は記録用で、記載した枚数を自動で上限にする機能ではありません。

### Step 3. 画像を再生成する（許可した範囲だけ）

```powershell
python -X utf8 scripts/pixai_batch.py generate --page 1 --batch-size 1 --execute --accept-warnings --confirm-credits --cost-note '残高○○、確認したモデル・設定で1ページ5コマを各1枚、合計5枚のクレジット消費を2026-10-25に許可'
```

- `--confirm-credits` は「この範囲のクレジット消費を許可した」というあなたの宣言です。スクリプトが無料を確かめるものではありません。
- １コマずつタスクを作り、完了を待って候補を `output/pixai/candidates/p01-02/r003.png` のように保存します。途中で失敗すると残りは送らずに止まり、自動で再送しません。
- 完了待ちの途中で止まった（ネットワークの切断・中止など）場合は、生成をやり直さずに `python -X utf8 scripts/pixai_batch.py fetch --page 1` で取得し直せます。PixAIの生成画像は無期限には保存されないため、早めに取得してください。

### Step 4. 採用してページを組み直す

```powershell
python -X utf8 scripts/pixai_batch.py list --page 1
python -X utf8 scripts/pixai_batch.py adopt p01-02 --candidate 3      # 見比べて選ぶ
python -X utf8 scripts/pixai_batch.py adopt-latest --page 1           # 各コマの最新をまとめて採用する場合
python -X utf8 scripts/pixai_batch.py build --page 1                  # PSDも作るときは --write-psd
```

結果は `output/build/page-01/vNNN/page-01.png`（確認用は `page-01-display.png`）です。

---

## 画面（WebUI）で操作する

ターミナルの代わりに、ブラウザーの画面で `.env.pixai` の変数・要求の編集（縦横比、mode、画風プリセット、LoRA）、生成、取得し直し、候補の採用、PNG／PSDのビルド、ページ送りのプレビューを行えます。

```powershell
python -X utf8 .agents/skills/pixai-batch-webui/pixai_webui.py
```

表示された `http://127.0.0.1:8775/?token=…` をブラウザーで開きます（AIエージェントはブラウザーを操作しないため、URLを案内するだけです）。終了は Ctrl+C。詳しくは `.agents/skills/pixai-batch-webui/SKILL.md`。

---

## 補助設定（`.env.pixai`）

`PIXAI_MODEL`・`PIXAI_QUALITY_TAGS`・`PIXAI_NEGATIVE_PROMPT`・`PIXAI_PROMPT_HELPER` は、`pixai_compose.py` で要求を組み立てるときに使います。変更しても既存の要求JSONは自動で変わりません。既存の要求に反映するには要求を編集・組み直してください。`PIXAI_CHECK_IDENTITY` は生成前の点検に使います。

```dotenv
# モデル（tsubaki2・tsubaki3・haruka2・hoshino2、またはモデルのバージョンID）
PIXAI_MODEL="tsubaki2"
# 品質タグの全文（空にすると付けない。既定は masterpiece, best quality）
PIXAI_QUALITY_TAGS="masterpiece, best quality"
# すべての要求に付ける既定の除外（書かなければこの４語が既定。空にすると付けない）
PIXAI_NEGATIVE_PROMPT="text, speech bubble, panel border, watermark"
# 送信前のプロンプトの自動書き換え（既定 disable。enable にすると字コンテとずれることがある）
PIXAI_PROMPT_HELPER="disable"
# 識別特徴の自動点検（1で有効。input/pixai/characters.json を使う）
PIXAI_CHECK_IDENTITY=1
```

要求JSONを新しく作る・作り直すときは `scripts/pixai_compose.py` を使います（例は [PixAI制作手順](../knowledge/pixai-composed-production.md#compose)）。画風プリセットの一覧は `python -X utf8 scripts/pixai_compose.py --list-styles` で見られます。

---

## よくあるエラーと対処法

| 表示・状況 | 主な原因 | 対処法 |
| --- | --- | --- |
| **使えない変数名** | 命名規則に合わない | `PIXAI_CHAR_`・`PIXAI_STYLE_`・`PIXAI_BACKGROUND_`・`PIXAI_LORA_` のどれかで始め、半角英大文字・数字・`_` にします |
| **変数 ○○ が .env.pixai 等にありません** | 変数が未設定 | `.env.pixai` に行があるか、`env-set` を実行したか確認します |
| **同じ変数が複数の場所にあります** | `.env.pixai` と環境変数の両方にある | どちらか１か所にします |
| **PIXAI_LORA_ の値はLoRAのバージョンID…** | LoRAの値に数字以外が入っている | URLの最後の数字だけを書きます |
| **費用未確認です** | `--confirm-credits` がない | 残高と範囲を確認し、許可する場合だけ付けます |
| **現行の公式文書にない項目があります** | i2i・インペイント・ControlNet・参照画像・v1のseed等を使う要求 | 使ってよい場合だけ `--allow-unverified` を付けます。受理と効果はキットで確かめたもの（`docs/knowledge/pixai-api.md`）もありますが、予告なく変わる可能性があります |
| **画像のない実行記録があります** | 完了待ちの途中で止まった、送信の結果が不明 | まず `fetch --ids p01-02`。taskIdがなく取得できない場合は、PixAIの画面で生成とクレジットを確認し、`move-unknown --ids p01-02 --confirm-checked --note '確認した内容'` で `failed/` へ移します（削除しません） |
| **HTTP 400 [入力エラー]** | 要求の値が受け付けられなかった（例：SDXLのモデルに mode） | 応答の内容を見て要求を直します。タスクは作られておらず、記録は自動で `failed/` へ移ります |
| **HTTP 429 [利用制限]** | 待機中のタスクが10件に達した等 | しばらく待ってから送ります |
| **設定を変えたのに画像が変わらない** | 再生成・採用・buildのどれかが未完了 | 生成 → `adopt` → `build` の順に確認します |

- **手順の正本**: [PixAI制作手順](../knowledge/pixai-composed-production.md#character-variables)、[PixAI APIの接続手順](../knowledge/pixai-api.md)
- **作品ごとのコマンドと採用記録**: [PixAI一括生成の記録](../production/PIXAI-BATCH.md)
