"""LoRA適用の外部処理（作品ごとに実装する差し込み口）。

この雛形は何もしない。利用者が「ComfyUIでLoRAを適用したい」等を依頼したときに、AIエージェントが
このファイルへ処理を書き、READY を True にする。WebUIの「LoRA適用モード」は、READY が True で、
apply があり、check() が (True, …) を返すときだけONにできる。

呼ばれ方（lora_run.py が１コマずつ呼ぶ）
  apply(job) -> dict | None
    job.root           作品ルート（Path）
    job.request_id     要求ID（例 p01-03）
    job.page           ページ番号（int、ページ外の要求は None）
    job.source_image   元にする画像（Path。採用中の画像または最新の候補。どちらもない場合は None）
    job.request        要求JSON（.env の ${変数} を展開済みの dict。プロンプト・人物別本文・寸法・seed 等）
    job.raw_request    要求JSON（展開前。${変数} のまま）
    job.output         書き出し先のPNG（Path。output/lora/<要求ID>/lNNN.png。このパスへ必ず保存する）
    job.work_dir       作業用フォルダ（Path。output/lora/<要求ID>/work/。中間ファイルを置いてよい）
    job.log            ログ出力の関数（job.log("…") でWebUIの実行ログへ出る）
  戻り値の dict は実行記録（lNNN.lora.json）の "result" に保存される（使ったモデル・LoRA名・強度・seed 等）。
  失敗したら例外を投げる。lora_run.py は残りを実行せずに止まり、自動で再試行しない。

check(root) -> (bool, str)
  ONにする前と実行前に呼ばれる。接続先（例：ComfyUIのURL）やモデル・LoRAファイルの有無を確かめ、
  使えない場合は (False, 理由) を返す。時間のかかる処理・生成・課金を伴う処理をここで行わない。

実装するときに守ること
  - 認証情報・APIキーをこのファイルやログ・記録へ書かない。必要なら環境変数や .secrets/ から読む。
  - 有料の外部サービスを使う場合は、利用者の明示の許可がある範囲だけで実行し、費用の確認方法を記録に残す。
  - 元の画像（NovelAIの候補）を上書きしない。結果は job.output にだけ書く。
  - 実装した内容・接続先・モデル・LoRA・強度の既定値と確認結果を、作品の docs/production/ の記録へ残す。
"""
from __future__ import annotations

NAME = "未実装"          # 例: "ComfyUI img2img + キャラLoRA"
VERSION = "0"
READY = False            # 実装と動作確認が終わったら True にする


def check(root) -> tuple[bool, str]:
    if not READY:
        return False, "LoRA適用の処理が未実装です（lora_apply.py の READY が False）。"
    return True, "準備済み"


def apply(job) -> dict | None:
    raise NotImplementedError("LoRA適用の処理が未実装です。lora_apply.py に処理を書いてください。")
