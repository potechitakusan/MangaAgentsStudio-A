# NovelAI一括生成の記録

NovelAIを使う作品で、人間がページ単位・全ページの生成をやり直し、採用画像を選び、同じ配置でPNG・PSDを組み直すための記録。手順は [NovelAIでの制作手順](../knowledge/novelai-composed-production.md#batch)。コマンドは作品ルートで実行する。

## 生成条件

- モデル・steps・費用条件の確認方法（`--cost-note` に書く内容の例）：
- 費用確認フラグ（確認済みの場合だけ付ける）：`--confirm-zero-anlas`、V5なら `--confirm-v5-allowance`

## 契約照会の頻度

契約・Anlas・V5利用上限の照会API（`/user/subscription`）は、最初の生成（おためし）で呼び、以後は前回の照会から数えて10回の生成ごとに1回にする（ユーザー指示、2026-10-05。API呼び出しの増えすぎを避けるため）。スクリプトが `output/novelai/subscription-check.json` で自動に数え、各生成の実行記録（`.novelai.json`）の `subscriptionCheck` に「API呼び出し／前回の結果を利用」を残す。モデル・寸法・steps・追加機能の変更、前回の生成の未完了、V5の利用上限が少ない場合は回数にかかわらず照会する。照会を強制するときは上のファイルを削除する。有料利用の許可、`--confirm-zero-anlas`・`--allow-anlas`・`--cost-note` は従来どおり各実行で必要。詳細は [Opusの手順](../knowledge/ai-production.md#novelai-opus)。

## ページごとのコマンド

| ページ | 要求（`input/novelai/requests/`） | 生成（送信なしの確認は `--execute` 以降を外す） | 組み直し |
| --- | --- | --- | --- |
| 1 |  | `python -X utf8 scripts/novelai_batch.py generate --page 1 --execute --accept-warnings --confirm-zero-anlas --cost-note '…'` | `python -X utf8 scripts/novelai_batch.py build --page 1` |

全ページ：`python -X utf8 scripts/novelai_batch.py generate --all --execute --accept-warnings …`、`python -X utf8 scripts/novelai_batch.py build --all`（PSDも作るときは `--write-psd`）。

候補の確認と採用：`python -X utf8 scripts/novelai_batch.py list --page 1` → 候補の画像を見比べる → `python -X utf8 scripts/novelai_batch.py adopt p01-02 --candidate 3`。

各フォルダの最大番号のPNGをまとめて採用：`python -X utf8 scripts/novelai_batch.py adopt-latest --page 1`（全ページは `--all`、特定コマは `--ids p01-02,p01-04`）。`--dry-run` を付けると対象の表示だけになる。新しい生成が失敗したコマでは以前の最大番号のPNGを選ぶため、生成結果と画像を確認して使う。詳細は [編集・再生成のREADME](../novelai-prompts/README.md#各フォルダの最新番号をまとめて採用する)。

## プロンプトの警告を残した理由

`generate` の送信なし確認で出た警告は、原則としてプロンプトを直す。残す場合だけ理由を書き、`--accept-warnings` を付けて送信する。

生成・再生成の実行例には `--accept-warnings` を既定で付けている。警告をチェックし、残っていれば送信を止めたい場合は外す。付けた場合も警告は表示され、費用確認・エラーの検証は省略されない。

| 要求ID | 警告 | 残した理由 | 日付 |
| --- | --- | --- | --- |
|  |  |  |  |

## 採用の記録

| 要求ID | 採用した候補 | 採用理由・見比べた点 | 採用者（人間／Codex）・日付 |
| --- | --- | --- | --- |
|  |  |  |  |

## 送信前の内容照合

プロンプト作成・修正時に `manga-ai-production` を使い、`docs/knowledge/novelai-composed-production.md` の「場面の関係と継続状態を各要求へ展開する」「送信前の内容照合」に従って記入する。本文・人物別本文・座標・否定文を変数展開後に照合する。自動警告の結果だけを転記しない。セリフ・文字・吹き出し・枠は後から組版する。

| 要求ID・確認した版 | 必須の関係（行為者・相手・接点等） | 直前から継続する状態／今回の変更 | 割り当て・矛盾・文字分離の照合結果／修正理由 |
| --- | --- | --- | --- |
|  |  |  |  |

## キャラクター・絵柄・背景の変数（依頼があった場合のみ）

| 変数名 | 人物・用途 | 使う要求 | 設定・確認日 |
| --- | --- | --- | --- |
|  |  |  |  |

値は作品ルートの `.env` にある。ここには値を写さず、変数名だけを書く。`NOVELAI_CHAR_*`・`NOVELAI_STYLE_*`・`NOVELAI_BACKGROUND_*` を使用できる。確認は `python -X utf8 scripts/novelai_batch.py vars`。編集・反映・再生成は [初心者向けREADME](../novelai-prompts/README.md)。
