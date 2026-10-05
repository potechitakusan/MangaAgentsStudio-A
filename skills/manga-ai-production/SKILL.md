---
name: manga-ai-production
description: キャラ参照絵やページ配置から漫画のページ・コマを生成・編集し、PNGプレビューで確認・修正して、指示のあるPSD原稿を人間へ引き渡すときや、表情・ポーズ・見た目の再現実験を行うときに使う。
---

# 漫画の画像制作とPSD引き渡し

このSkillは漫画プロジェクト一式に同梱する。以下のパスは作業対象プロジェクトのルート基準。配布元で原本を試す場合は重点設定に `templates/manga-project/config/review-profiles.json` を指定する。

対象シーン・狙い・入力（あらすじ/字コンテ/ネーム/原稿/参照絵）を確認し、`docs/knowledge/review-workflow.md` に従って実効重点を読む。担当する主観点は `characterConsistency`。内容の判断には `docs/knowledge/ai-production.md` の該当箇所を参照する。

QwenやNovelAI等へ画像を条件として渡し、コマ別に作画する方式を選んだ場合は、同梱の `manga-external-panel-i2i` と `docs/knowledge/external-panel-i2i.md` へ進む。モデル固有の入力・症状は該当モデル文書、接続・料金はサービス文書を参照する。接続確認だけ、文字だけの生成、imagegenによる新規のコマ・ページ作画にはこの分岐を強制しない。Qwen-Image 2.1の制作記録とQwen-Image-Edit-2511の資料を区別する。

ページ作画の生成前は `docs/knowledge/panel-layout-policy.md` を読み、テンプレートの採用ID、または演出上の独自配置とその理由をページ別記録へ残す。原則テンプレートを使用し、ユーザーの必須・不使用指定を優先する。imagegenでは番号付きレイアウト画像と各コマの内容を実際に画像入力・指示へ渡し、ページ全体の一括生成を基本とする。独自配置でも参照画像を用意し、必要時のコマ別生成は理由を記録する。枠・吹き出し・文字を含めた生成を一律禁止せず、生成後に計画・原文と照合して番号等の混入やずれを修正する。キャラ参照絵だけの生成にはページ配置を要求しない。NovelAI等は各環境の制作手順に従う。

NovelAIを使うときは `docs/knowledge/ai-production.md` のOpus節を読む。OpusならAnlas消費なしを既定とし、寸法・Steps・１回の枚数・追加機能とV5の利用上限を確認する。採用寸法は `config/page-layout.json` と生成ツールへ反映し、枠・最終PNGは `docs/knowledge/page-layout.md` に従って生成実寸に合わせる。0 Anlasを確認できない生成を試験送信せず、有料利用は既に明示された指示の範囲でのみ行う。契約・Anlas・V5利用上限の照会APIは、最初の生成で呼び、以後は目安10回の生成ごとに1回にする（スクリプトが自動で数える。API呼び出しの増えすぎを避けるため。条件の変更・前回の未完了・V5の残量が少ない場合は毎回）。有料利用の許可と費用確認の指定は従来どおり。NovelAIのコマ素材は `docs/knowledge/novelai-composed-production.md` に従い、本番前に人物試作を１回生成して外見を照合し、コマの形に近い縦横比で生成する。コマより広い範囲を生成して最上段のコマ枠とマスクで必要な部分を見せ、拡大しすぎて字コンテの主対象・動作・画角を失わない。要求のプロンプトは `docs/knowledge/novelai-composed-production.md` の「要求プロンプトの組み立て」に従い、`generate` の警告を直してから送信する。NovelAIで組版してPNGプレビューを作ったら、`docs/knowledge/novelai-composed-production.md` の「PNGプレビューをページ送りで確認するHTML」に従い、ページ送り用のHTMLを作って提示する（ブラウザーは起動しない）。要求は１コマ１JSONで `input/novelai/requests/` に保存し、NovelAI APIで生成する要求は原則として `scripts/novelai_compose.py`（V5が既定、V4.5はユーザーが指定した場合だけ）で組み立てる。i2iや参照などの追加機能で改造が必要な場合は、これを元に改造して使う（送信・費用確認は `novelai_batch.py`・`novelai_api.py` を通す）。生成・採用・組み直しは `scripts/novelai_batch.py` で行い、人間が再実施できるコマンドを `docs/production/NOVELAI-BATCH.md` に残す。キャラクター・絵柄・背景の `.env` 変数化は人間の依頼がある場合だけ、変数名と内容を確認して行う。導入・編集は `docs/knowledge/novelai-composed-production.md` の変数化の節、利用者向けの変更例は `docs/novelai-prompts/README.md` を参照する。

### NovelAIのプロンプト組み立て・送信前確認

NovelAI用の要求を作成・修正・点検する場合だけ、`docs/knowledge/novelai-composed-production.md` の「場面の関係と継続状態を各要求へ展開する」「送信前の内容照合」を必ず読む。関係・継続状態を実要求へ展開して照合し、セリフ・文字・吹き出しは後から組版する。imagegenだけを使う作業では、この詳細文書とNovelAI用の照合記録を読み込まず、この節の方式を適用しない。

NovelAIで人物・物の画面内位置を指定する場合は、同文書の「配置ピン（Character Positions）」を読む。必要なコマで人物別入力と配置ピンを使い、プロンプトの順序・左右の記述・組版後の切り抜きと整合させる。APIの `use_coords`・`centers` の書式は `docs/knowledge/novelai-api.md` の「配置ピンの要求」を参照する。全コマでの使用を必須にせず、NovelAI以外の生成・編集には適用しない。

文字・吹き出しは `docs/knowledge/page-layout.md` の「文字・吹き出しの仕上げ」に従い、imagegenでは画像に含めて生成するのを基本とし、imagegen以外では作画後に別に載せる。作画前に使用手段から判断し、組版方法の回答を制作開始条件にしない。

作画後は画像を実際に開き、`docs/reviews/NAME-REVIEW.md` の「作画後の照合表」をコマごとに記入する。別組版する場合は組版前に照合を終え、`scripts/typeset_manga.py` の点検結果と原画入りの確認画像を使って「組版後の点検」を記入する。imagegenで文字・吹き出し込みで生成した場合は生成後に完成ページを照合・点検する。文字・フキダシ・画中の文字の扱いは `docs/knowledge/japanese-manga-readability.md` に従い、依頼にない作品名・ページ番号を入れない。

キャラの固定特徴、参照絵、変更したい要素、利用可能な環境を確認する。反復比較はComfyUI、局所編集は利用可能な画像編集機能を候補とし、NovelAI出力をComfyUIで絵柄へ寄せる場合は元の特徴を残す条件も記録する。指定モデル名の実在と互換性を調べ、未導入を勝手に導入済みと扱わない。seed固定だけでキャラ一貫性を保証しない。実験はdocs/experiments/TEMPLATE.mdの形式で条件・試行数・失敗・結果を残し、未生成なら未実証と明示する。認証キーの値を回答やログへ書かない。画像生成・編集時は環境にある対応Skillの必要な手順を確認し、提供されていないツール/APIをあるものとして実行しない。

結果は対象箇所、観察、読者への影響の仮説、重大度、改善案、失う効果を含める。依頼が相談なら提案と選択理由を示す。レビューでは問題なしや判断不能も正直に記録する。最終的な採否はメインエージェントが統合して `docs/reviews/` に残し、再利用できる結果のフィードバックは、ユーザーが記録を依頼した場合だけ `docs/feedback/` に残す。依頼がなければ記録するかの確認も行わない。

漫画を完成させる依頼では `docs/knowledge/manga/08-workflow-review.md` と `docs/knowledge/psd-handoff.md` を読み、まず制作素材からPNGプレビューを作成・点検して提示する。修正があれば反映・再提示し、最新のPNGについてユーザーに修正がないことを確認する。PSD作成の指示がなければ作るか聞いて回答を待ち、まだ作らない。PNGへの「修正なし」や返答なしをPSD作成指示とみなさない。既に作成指示がある場合は再確認せず、PNGの修正確認後にPSDの作成・検証・引き渡しへ進む。

絵・文字・フキダシなど実際に分けて制作できる範囲をPSD作成前から保持し、確定セリフを `docs/production/DIALOGUE.md` に残す。確認対象のPNG・版・回答とPSD作成指示の有無を `docs/production/PSD-HANDOFF.md` と進捗へ記録する。依頼されたPSDは再読込・レイヤー・確認済みPNGとの合成結果の照合・全ページの通読を行い、仕様・未確認事項・統合済みの箇所・人間に残す仕上げを記録して引き渡す。PNG確認待ち・PSD作成回答待ちは正規の待機段階とする。PNGだけ・相談・部分生成だけの依頼はその対象で完了する。

原則、人間がCLIP STUDIO PAINTで仕上げてから外部公開する。CBZはユーザーの明示指定時だけ作成する。PSDに文字層があってもCLIP STUDIO PAINTで文字が再編集できると仮定しない。実読込を確認できない場合は未確認と明記する。説明とレイヤー名は日本語にする。
