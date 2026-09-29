# NovelAI一括生成の記録

NovelAIを使う作品で、人間がページ単位・全ページの生成をやり直し、採用画像を選び、同じ配置でPNG・PSDを組み直すための記録。手順は [NovelAIでの制作手順](../knowledge/novelai-composed-production.md#batch)。コマンドは作品ルートで実行する。

## 生成条件

- モデル・steps・費用条件の確認方法（`--cost-note` に書く内容の例）：
- 費用確認フラグ（確認済みの場合だけ付ける）：`--confirm-zero-anlas`、V5なら `--confirm-v5-allowance`

## ページごとのコマンド

| ページ | 要求（`input/novelai/requests/`） | 生成（送信なしの確認は `--execute` 以降を外す） | 組み直し |
| --- | --- | --- | --- |
| 1 |  | `python -X utf8 scripts/novelai_batch.py generate --page 1 --execute --confirm-zero-anlas --cost-note '…'` | `python -X utf8 scripts/novelai_batch.py build --page 1` |

全ページ：`python -X utf8 scripts/novelai_batch.py generate --all --execute …`、`python -X utf8 scripts/novelai_batch.py build --all`（PSDも作るときは `--write-psd`）。

候補の確認と採用：`python -X utf8 scripts/novelai_batch.py list --page 1` → 候補の画像を見比べる → `python -X utf8 scripts/novelai_batch.py adopt p01-02 --candidate 3`。

## プロンプトの警告を残した理由

`generate` の送信なし確認で出た警告は、原則としてプロンプトを直す。残す場合だけ理由を書き、`--accept-warnings` を付けて送信する。

| 要求ID | 警告 | 残した理由 | 日付 |
| --- | --- | --- | --- |
|  |  |  |  |

## 採用の記録

| 要求ID | 採用した候補 | 採用理由・見比べた点 | 採用者（人間／Codex）・日付 |
| --- | --- | --- | --- |
|  |  |  |  |

## キャラ別プロンプトの変数（依頼があった場合のみ）

| 変数名 | 人物・用途 | 使う要求 | 設定・確認日 |
| --- | --- | --- | --- |
|  |  |  |  |

値は作品ルートの `.env` にある。ここには値を写さず、変数名だけを書く。確認は `python -X utf8 scripts/novelai_batch.py vars`。
