---
name: pixai-batch-webui
description: PixAIで制作中の作品を、ブラウザーの画面から操作したいとき（.env.pixai のキャラクター・絵柄・背景・LoRAの変数、要求JSONのプロンプト・縦横比・mode・画風プリセット・LoRAの編集、生成・完了待ちが途切れた結果の取得し直し・候補の採用・ページのビルド・プレビュー）に使う。作品の pixai_batch.py・pixai_api.py をそのまま呼ぶローカルWebUIを起動して案内する。
---

# PixAI制作のWebUI

`docs/knowledge/pixai-composed-production.md` の一括生成（要求JSON → generate → adopt → build）を、人間が画面で操作するための道具。処理はすべて作品の `scripts/pixai_batch.py`・`scripts/pixai_api.py` に任せる。WebUIは独自の生成・組版をしない。

## 起動（作品ルートで）

```powershell
python -X utf8 .agents/skills/pixai-batch-webui/pixai_webui.py
# ポートや作品を指定する場合
python -X utf8 .agents/skills/pixai-batch-webui/pixai_webui.py --port 8800 --root <作品ルート>
```

表示された `http://127.0.0.1:8775/?token=…` を利用者がブラウザーで開く。**AIエージェントはブラウザーを起動・操作しない**（URLを伝えるだけ）。終了は Ctrl+C。URLのトークンは起動ごとに変わる。既定のポート（8775）は、他の制作パネル（8765）と同時に起動できるよう分けている。

## 画面でできること

| タブ | 内容 | 呼ぶコマンド |
| --- | --- | --- |
| コマ | 要求の一覧（ページ別、採用画像のサムネイル、`[v2]`・`[v1]` の別、画像のない記録の件数）。v2 の要求は項目で編集する：プロンプト、除外、モデル（modelVersionId）、縦横比と解像度（出力の画素数を表示）、mode（Tsubaki.2・Tsubaki.3 系）、画風（プリセット・自由記述。Tsubaki.2・Tsubaki.3 系）、LoRA（最大5件。バージョンID・重み・トリガー語。`${PIXAI_LORA_…}` も可）、seed、枚数（1・4）、promptHelper、sampling（SDXL）。v1 の要求（i2i・ControlNet・参照画像・Hires・ADetailer）は prompts と parameters のJSONで編集する。差し替え案（`p01-03b` 等）として複製。変数展開後の送信内容と語の点検の表示。候補の比較・拡大・採用・廃棄（`discarded/` へ移す）。１タスク4枚（`batchSize` 4）の候補は「同じ生成の4枚」としてまとめて表示し、その中から採用する。生成のダイアログで１コマの枚数（自動＝作り直しは4枚・4枚・1枚）を選べる。画像のない記録があるコマでは「PixAIから取得し直す」。ページ単位・全ページ・指定ページから指定ページまでの生成と、最新候補の一括採用 | `generate`（`--max`・`--batch-size`）、`fetch`、`adopt`、`adopt-latest` |
| ページ | 最新ビルドと注記入り確認画像、組版点検の件数。コマ内の focus・zoom・rotation の表、ページ構成と組版指定のJSON編集。ページ単位・全ページのそれぞれに「PNG」と「PSD」のビルドボタン（PSDのビルドは同じ版のPNGも作る） | `build`、`build --write-psd`（`--page`／`--all`） |
| 変数 | `.env.pixai` の `PIXAI_CHAR_`・`PIXAI_STYLE_`・`PIXAI_BACKGROUND_`・`PIXAI_LORA_` の表示・編集・追加、使う要求の一覧、その要求の生成、templatize（確認／適用）。左側に、プロンプトを一括で調整できるようにするためのAIエージェントへの依頼文の例を表示し、変数が１個もない場合は「変数を追加」の上に赤い太字でも表示する | `env-set`、`templatize` |
| プレビュー | 各ページの最新ビルドをページ送り（右から左。← が次） | ― |
| 実行ログ・接続 | 直前の操作のコマンドと出力（実行中も1.2秒ごとに更新。タスクの状態 waiting・running も表示）、実行中の操作の中止、**実行結果の整理**（下記）、キーの読込確認、接続確認（画像生成なし）、list | `key-status`、`status`、`list` |

各操作は、同じことを端末で行うコマンドをログに表示する（`output/webui-pixai/logs/` にも保存）。

## 実行結果の整理（実行ログ・接続タブ）

要求ID（例 `p07-03`）を入れて「点検」、または「全コマから画像なしの記録を探す」で使う。**ファイルは削除せず、同じフォルダのサブフォルダへ移す**（`moved.json` に操作を残す。操作は `output/webui-pixai/logs/records.log` にも記録）。実行中の操作がある間は整理できない。

| 状態 | 対応 |
| --- | --- |
| 画像のない記録で taskId がある（完了待ちの途中で止まった・中止した・画像の取得に失敗した） | 「PixAIから取得し直す（fetch）」。タスクを照会し、完了していれば画像を保存する。生成は再送しない。PixAIの生成画像は無期限には保存されないため、早めに取得する |
| 画像のない記録で taskId がない（送信の応答を受け取れなかった） | PixAIの画面で生成とクレジットの消費を確認し、「確認した」にチェックして `failed/` へ移す。画像ができていた場合は、その画像を `rNNN.png` として同じフォルダに保存すれば結果として扱える |
| 不要な候補 | 「廃棄」で `discarded/` へ移す。採用中の画像は廃棄できない。`discarded/` から「戻す」で元の場所へ戻せる（同名があれば戻さない） |
| 止まらない操作 | 「中止」。作成済みのタスクはPixAI側で続くため、記録は画像なしで残る（上の fetch で取得する）。ビルドを中止した場合は、未完成の版フォルダ（`build.json` がない）を確認して片づける |

PixAIがタスクを作らずに拒否した場合（HTTP 4xx）や、タスクが failed・cancelled で終わった場合は、`pixai_api.py` が自動で記録を `failed/` へ移す（候補の番号は空く）。端末では `python -X utf8 scripts/pixai_batch.py fetch --ids <要求ID>`、`move-unknown --ids <要求ID> --confirm-checked --note '確認した内容'` で同じことができる。

## 守ること

- **生成の費用確認は省略しない。** PixAIのクレジットの残高・消費を照会するAPIは公式文書にないため、スクリプトは無料を判定しない。「生成する」には、**利用者がこの範囲のクレジット消費を明示的に許可した**ことを確認したチェック（`--confirm-credits`）と確認内容（`--cost-note`）が必須。AIエージェントは、利用者の明示の許可がないままチェックを付けるよう案内しない。
- 現行の公式文書にない項目（v1 の i2i・ControlNet・IP-Adapter・seed・除外など）を使う要求は、利用者が試すことを了承した場合だけ「未確認の項目」のチェック（`--allow-unverified`）を付ける。
- 生成画面のチェックと上限件数は、**起動ごとのトークン（URL）単位でブラウザーに記憶する**。サーバーを起動し直して新しいURLで開くと、古いトークンの記憶は消える。記憶したチェックも確認済みの宣言なので、範囲（タスク数・枚数・モデル・mode・解像度・LoRA・追加機能）を変えた場合は外して確認し直す。
- 1回の上限件数は既定30タスク（`pixai_batch.py` の既定）。１タスク4枚の要求は4枚分を使う。送信間隔（既定3秒）・ポーリング間隔（3秒から10秒。公式は1.5秒に1回以下）・失敗時に止まって自動再送しない扱いは `pixai_batch.py` のまま。同時に１つの操作だけ実行する。
- APIキーは読まない・表示しない（変数は `pixai_batch.read_variables` が許可した接頭辞だけを扱う）。画像は `output/`・`input/`・`templates/onomatopoeia/` の画像だけを返す。
- 127.0.0.1 でだけ待ち受け、起動時のトークンと Host を確かめる。他の端末へ公開しない。
- JSONを保存するたびに、前の内容を `output/webui-pixai/history/` に残す。保存前に JSON の形（v2 は `api`・`body.prompt`、v1 は `api`・`parameters.prompts`、ページ構成の `schema_version`・`panels`）を確かめる。
- 画面での編集も、作品の制作手順（要求プロンプトの組み立て、送信前の内容照合、作画後の照合表、組版後の点検、PNG確認・PSD作成の判断）を置き換えない。生成後は画像を開いて照合する。
- 変数化（`.env.pixai` への取り込み）は、作品の手順どおり人間の依頼があった場合に、変数名と値を確認してから行う。

## 前提と限界

- Python 3.10以上の標準ライブラリだけで動く。build と WebP・JPEG の応答のPNG変換は作品の既存要件（Pillow）を使う。
- 対応するのは配布版0.5系の `pixai_batch.py`（`read_variables`・`request_files`・`candidates`・`unknown_records`・`load_adopted`・`resolved_request`・`lint_prompt` 等の関数と、list・vars・env-set・templatize・generate・fetch・adopt・adopt-latest・build の各コマンド）。関数名が変わった版では起動時にエラーになる。
- 要求の新規作成、v2 と v1 の切り替え、人物の追加・削除は画面に出していない（`pixai_compose.py` で組み立てるか、JSONを直接編集する）。
- ページ構成の `request` は `input/pixai/adopted.json` の採用画像を使う。NovelAI等の他の手段で作った画像を同じページに置くコマは、`request` ではなく `source` に画像のパスを書く。
