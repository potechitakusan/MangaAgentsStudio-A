# PixAI一括生成の記録

PixAIを使う作品で、人間がページ単位・全ページの生成をやり直し、採用画像を選び、同じ配置でPNG・PSDを組み直すための記録。手順は [PixAIでの制作手順](../knowledge/pixai-composed-production.md#batch)。コマンドは作品ルートで実行する。

## 生成条件と費用の許可

- モデル・mode・縦横比と解像度・１タスクの枚数・LoRA・画風プリセット：
- 利用者が許可したクレジット消費の範囲（タスク数・枚数・日時）：
- `--cost-note` に書く内容の例（残高・会員プラン・許可の範囲）：
- 公式文書にない項目（i2i・インペイント・ControlNet・latentCouple・IP-Adapter・v1のseed・除外）を使うことの了承：あり／なし（ありの場合だけ `--allow-unverified`）

クレジットの残高・消費を照会するAPIは公式文書にない。実消費は利用者がPixAIの画面で確認し、必要ならここへ書く。

| 日付 | モデル・mode・解像度 | タスク数・１タスクの枚数 | 消費クレジット（利用者が画面で確認） | 備考 |
| --- | --- | --- | --- | --- |
| 2026-10-25（例） | Tsubaki.3・pro・1k | 1タスク・1枚／1タスク・4枚 | 4,000／7,000 | 利用者がPixAIの利用履歴で確認した例 |
|  |  |  |  |  |

## ページごとのコマンド

| ページ | 要求（`input/pixai/requests/`） | 生成（送信なしの確認は `--execute` 以降を外す） | 組み直し |
| --- | --- | --- | --- |
| 1 |  | `python -X utf8 scripts/pixai_batch.py generate --page 1 --execute --accept-warnings --confirm-credits --cost-note '…'` | `python -X utf8 scripts/pixai_batch.py build --page 1` |

完了待ちが途切れた記録の取得し直し：`python -X utf8 scripts/pixai_batch.py fetch --page 1`（生成は再送しない）。候補の採用：`list --page 1` → 画像を見比べる → `adopt p01-02 --candidate 3`、または `adopt-latest --page 1`。

## プロンプトの警告を残した理由

| 要求ID | 警告 | 残した理由 | 日付 |
| --- | --- | --- | --- |
|  |  |  |  |

## 採用の記録

| 要求ID | 採用した候補 | 採用理由・見比べた点 | 採用者（人間／Codex）・日付 |
| --- | --- | --- | --- |
|  |  |  |  |

## 送信前の内容照合

`docs/knowledge/pixai-composed-production.md` の「場面の関係と継続状態を各要求へ展開する」「送信前の内容照合」に従って記入する。プロンプト・除外・LoRA・参照画像を変数展開後に照合する。

| 要求ID・確認した版 | 必須の関係（行為者・相手・接点等） | 直前から継続する状態／今回の変更 | 主語・LoRA・参照画像・文字分離の照合結果／修正理由 |
| --- | --- | --- | --- |
|  |  |  |  |

## 公式文書にない機能を使った結果

| 要求ID | 機能（i2i・ControlNet・IP-Adapter 等） | 受理されたか・効果・気づいた点 | 日付 |
| --- | --- | --- | --- |
|  |  |  |  |

## キャラクター・絵柄・背景・LoRAの変数（依頼があった場合のみ）

| 変数名 | 人物・用途 | 使う要求 | 設定・確認日 |
| --- | --- | --- | --- |
|  |  |  |  |

値は作品ルートの `.env.pixai` にある（APIキー・URLは共通設定の `.env`）。ここには値を写さず、変数名だけを書く。確認は `python -X utf8 scripts/pixai_batch.py vars`。編集・反映・再生成は [利用者向けREADME](../pixai-prompts/README.md)。
