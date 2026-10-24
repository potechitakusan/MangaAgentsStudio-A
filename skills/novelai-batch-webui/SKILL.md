---
name: novelai-batch-webui
description: NovelAIで制作中の作品を、ブラウザーの画面から操作したいとき（.env のキャラクター・絵柄・背景の変数、要求JSONのプロンプト・配置ピンの編集、生成・候補の採用・ページのビルド・プレビュー）や、作品ごとの外部処理でLoRAを適用したいとき（lora_apply.py の実装）に使う。作品の novelai_batch.py・novelai_api.py をそのまま呼ぶローカルWebUIを起動して案内する。
---

# NovelAI制作のWebUI

`docs/knowledge/novelai-composed-production.md` の一括生成（要求JSON → generate → adopt → build）を、人間が画面で操作するための道具。処理はすべて作品の `scripts/novelai_batch.py`・`scripts/novelai_api.py` に任せる。WebUIは独自の生成・組版をしない。

## 起動（作品ルートで）

```powershell
python -X utf8 .agents/skills/novelai-batch-webui/novelai_webui.py
# ポートや作品を指定する場合
python -X utf8 .agents/skills/novelai-batch-webui/novelai_webui.py --port 8800 --root <作品ルート>
```

表示された `http://127.0.0.1:8765/?token=…` を利用者がブラウザーで開く。**AIエージェントはブラウザーを起動・操作しない**（URLを伝えるだけ）。終了は Ctrl+C。URLのトークンは起動ごとに変わる。

## 画面でできること

| タブ | 内容 | 呼ぶコマンド |
| --- | --- | --- |
| コマ | 要求の一覧（ページ別、採用画像のサムネイル）。場面共通の文（`input` と `base_caption` を同時に保存）、人物別本文、配置ピン（x・y、`use_coords`）、人物別の除外、除外文、幅・高さ・seed の編集。差し替え案（`p01-03b` 等）として複製。変数展開後の送信内容と語の点検の表示。候補の比較・拡大・採用・廃棄（`discarded/` へ移す）。ページ単位・全ページ・指定ページから指定ページまでの生成と、最新候補の一括採用（ページ単位・全ページ） | `generate`（`--max`）、`adopt`、`adopt-latest` |
| ページ | 最新ビルドと注記入り確認画像、組版点検の件数。コマ内の focus・zoom・rotation の表、ページ構成と組版指定のJSON編集。ページ単位・全ページのそれぞれに「PNG」と「PSD」のビルドボタン（PSDのビルドは同じ版のPNGも作る） | `build`、`build --write-psd`（`--page`／`--all`） |
| 変数 | `.env` の `NOVELAI_CHAR_`・`NOVELAI_STYLE_`・`NOVELAI_BACKGROUND_` の表示・編集・追加、使う要求の一覧、その要求の生成、templatize（確認／適用） | `env-set`、`templatize` |
| プレビュー | 各ページの最新ビルドをページ送り（右から左。← が次） | ― |
| 実行ログ・接続 | 直前の操作のコマンドと出力（実行中も1.2秒ごとに更新。自動スクロールのチェックをONにすると更新のたびに一番下を表示）、実行中の操作の中止、**実行結果の整理**（下記）、キーの読込確認、契約照会、list。失敗したときの「ログを開く」で、この画面が表示される。右上の状態表示には生成の進み具合（例：3/39件目 p01-03）が出て、クリックするとログを開く | `key-status`、`status`、`list` |

各操作は、同じことを端末で行うコマンドをログに表示する（`output/webui/logs/` にも保存）。

## 実行結果の整理（実行ログ・接続タブ）

要求ID（例 `p07-03`）を入れて「点検」、または「全コマから結果不明を探す」で使う。**ファイルは削除せず、同じフォルダのサブフォルダへ移す**（日時・候補番号・識別子でフォルダを分け、`moved.json` に操作を残す。操作は `output/webui/logs/records.log` にも記録）。復元した候補の `moved.json` は `output/webui/history/records/` へ保管する。実行中の操作がある間は整理できない。

| 状態 | 対応 |
| --- | --- |
| 結果不明（実行記録はあるが画像がない。`novelai_batch.py` が「結果不明の実行記録があります…failed/ へ移してから」で止まる） | NovelAIの画像の履歴とAnlasの消費を確認し、「確認した」にチェックして `failed/` へ移す。画像ができていた場合は、その画像を `rNNN.png` として同じフォルダに保存すれば結果として扱える（移さない） |
| 不要な候補 | 「廃棄」で `discarded/` へ移す。採用中の画像は廃棄できない。`discarded/` から「戻す」で元の場所へ戻せる（同名があれば戻さない） |
| LoRA適用の失敗・中断（`output/lora/` の結果不明）・不要な結果 | NovelAIと同じ操作（`failed/`・`discarded/`・戻す） |
| 止まらない操作 | 「中止」（実行中の操作の欄）。生成の送信中に中止すると、その記録は結果不明になるので上の手順で確認する。ビルドを中止した場合は、未完成の版フォルダ（`build.json` がない）を確認して片づける |

端末では、NovelAIの結果不明の記録を `python -X utf8 scripts/novelai_batch.py move-unknown --ids <要求ID> --confirm-checked --note '確認した内容'` で同じように `failed/` へ移せる（`--confirm-checked` なしは対象の表示だけ）。

`failed/`・`discarded/` の中は候補の番号の数え方・一覧の対象外になる（`novelai_batch.py` はフォルダ直下だけを数える）。

## LoRA適用モード

画面上部のタブの右にあるトグル。**作品ごとに実装する外部処理**（例：ComfyUIでキャラクターLoRAを使った img2img）で、採用中の画像や最新の候補にLoRAを適用するためのモード。

| ファイル | 役割 |
| --- | --- |
| `lora_apply.py` | 外部処理の差し込み口。**配布時は空**（`READY = False`、`apply` は未実装の例外） |
| `lora_run.py` | 指定したコマへ `lora_apply.apply(job)` を１件ずつ順に呼ぶ。結果は `output/lora/<要求ID>/lNNN.png` と実行記録 `lNNN.lora.json`。`--adopt` で採用（`novelai_batch.py adopt --file` と同じ処理）。失敗したら止まり、自動で再試行しない |

- 表示：未実装なら「LoRA適用モード（準備は未実施）」。ONにしようとすると、`READY` が True・`apply` がある・`check(root)` が `(True, …)` を返すかをサーバーが確かめ、満たす場合だけONにできる。状態は `output/webui/settings.json` に保存し、起動時と実行前にも確かめ直す（準備が崩れていればOFF扱い）。
- ONの間だけ、「全ページをLoRA適用…」（コマ一覧の上・ページ一覧の上）、ページごとの「LoRA適用」（コマ一覧の各ページ見出し）、「このページをLoRA適用…」（ページ画面）、「このコマをLoRA適用…」（コマ画面）、「範囲をLoRA適用…」（指定ページから指定ページまで）が表示される。コマ画面には `output/lora/` の結果と「採用」ボタンが出る（OFFでも結果は表示）。
- 元画像は「採用中の画像（未採用は最新の候補）」か「最新の候補」から選ぶ。NovelAIの候補・実行記録は変更しない。

### AIエージェントが lora_apply.py を実装するとき

利用者から「ComfyUIでLoRAを使いたい」等の依頼があった場合だけ行う。

1. 使う環境（ComfyUIのURL・ワークフロー、モデル、LoRAファイル名と強度、img2imgの強度、プロンプトの使い方）と費用・利用条件を利用者に確認する。有料サービスは明示の許可がある範囲だけ。
2. `lora_apply.py` の docstring の約束（`job.source_image`・`job.request`（.env 展開済み）・`job.output` へ必ず保存・`job.log`・戻り値は記録に残る dict）に従って `apply(job)` を書く。`check(root)` には接続先・ファイルの有無の確認だけを書く（生成・課金をしない）。
3. 認証情報をファイル・ログ・記録に書かない（環境変数や `.secrets/` から読む）。元画像を上書きしない。
4. 1コマで試し、結果画像を開いて確認してから `READY = True` にする。実装内容・既定値・確認結果を作品の `docs/production/` に記録する。
5. 作品固有の実装（URL・LoRA名など）を配布元へ戻さない。配布元の `lora_apply.py` は空の雛形のまま保つ。

## 守ること

- **生成の費用確認は省略しない。** 「生成する」には、0 Anlasを確認したチェックと確認内容（`--cost-note`）が必須。V5の利用上限のチェックはV5のとき付ける。WebUIは有料生成（`--allow-anlas`）を提供しない。有料利用は利用者の明示指示のもとで端末から行う。チェックは確認済みの宣言で、WebUIやスクリプトが無料を保証するものではない。
- 生成画面のチェック（0 Anlas・V5の利用上限・警告の確認）と上限件数は、**起動ごとのトークン（URL）単位でブラウザーに記憶する**。サーバーを起動し直して新しいURLで開くと、古いトークンの記憶は消える。記憶したチェックも確認済みの宣言なので、条件（モデル・寸法・steps・追加機能）を変えた場合や利用上限が少ない場合は外して確認し直す。
- 1回の上限件数は既定30件（`novelai_batch.py` の既定）。全ページなど30件を超える対象は、生成画面の「１回の上限件数」（`--max`、1～1000）を増やす。送信間隔（既定3秒）・失敗時に止まって自動再送しない扱い・結果不明の記録の扱いは `novelai_batch.py` のまま。同時に１つの操作だけ実行する。
- APIキーは読まない・表示しない（変数は `novelai_batch.read_variables` が許可した接頭辞だけを扱う）。画像は `output/`・`input/`・`templates/onomatopoeia/` の画像だけを返す。
- 127.0.0.1 でだけ待ち受け、起動時のトークンと Host を確かめる。他の端末へ公開しない。
- JSONを保存するたびに、前の内容を `output/webui/history/` に残す。保存前に JSON の形（`input`・`parameters`、ページ構成の `schema_version`・`panels`）を確かめる。
- 画面での編集も、作品の制作手順（要求プロンプトの組み立て、送信前の内容照合、作画後の照合表、組版後の点検、PNG確認・PSD作成の判断）を置き換えない。生成後は画像を開いて照合する。
- 変数化（`.env` への取り込み）は、作品の手順どおり人間の依頼があった場合に、変数名と値を確認してから行う。

## 前提と限界

- Python 3.10以上の標準ライブラリだけで動く。build は作品の既存要件（Pillow）を使う。
- 対応するのは配布版0.5系の `novelai_batch.py`（`read_variables`・`request_files`・`candidates`・`load_adopted`・`resolved_request`・`lint_prompt` 等の関数と、list・vars・env-set・templatize・generate・adopt・adopt-latest・build の各コマンド）。関数名が変わった版では起動時にエラーになる。
- 要求JSONの人物を追加・削除する編集、`v4_prompt` がない要求の人物別入力、steps・モデルの変更は画面に出していない（JSONを直接編集するか `novelai_compose.py` で組み立て直す）。
