# 文書の入口

このフォルダは制作キットの保守・配布用です。まず `scripts/New-MangaProject.ps1`（Linuxでは `scripts/New-MangaProject.sh`）でキット外に作品プロジェクトを作り、表示された絶対パスのフォルダでCodex（または指定したAIエージェント）を開き直します。その作品側で[制作プロセス](knowledge/manga/08-workflow-review.md)に沿い、企画からPNG確認、指示のあるPSDの引き渡しまでを進めます。キット内での制作は[READMEの例外手順](../README.md#どうしてもこのキット内で漫画を作る場合の例外)がそろうまで始めません。

## 1. はじめて使う人・利用者向けガイド

| 目的 | 参照先 | 対象読者・配布の扱い |
| --- | --- | --- |
| できること・必要環境・最初の依頼例を知る | [リポジトリのREADME](../README.md)・[公開作例一覧](../examples/README.md) | 初見・利用者向け（作例はキット側のみ） |
| 作成した作品フォルダで最初にやること・キー設定 | [作品側の環境設定（SETUP）](../templates/manga-project/docs/SETUP.md)・[作品のREADME](../templates/manga-project/README.md) | 利用者・エージェント共通（新規作品へ同梱） |
| 作成先フォルダでCodexを開き直す | [作成後の案内と、手順がわからない場合の対応](knowledge/codex-operation.md#作品フォルダでcodexを開き直す) | 利用者・エージェント共通（新規作品へ同梱） |
| 追加設定なしでWeb用PNGを作る・寸法や余白を変える | [ページの寸法・基本枠](knowledge/page-layout.md)、[オプション](../templates/manga-project/OPTION.md) | 利用者・エージェント共通（新規作品へ同梱） |
| NovelAIのキャラ・絵柄・背景を変数で編集して再生成する | [NovelAIプロンプト編集README](../templates/manga-project/docs/novelai-prompts/README.md) | 利用者向け（新規作品へ同梱） |
| PixAIのキャラ・絵柄・背景・LoRAを変数で編集して再生成する | [PixAIプロンプト編集README](../templates/manga-project/docs/pixai-prompts/README.md) | 利用者向け（新規作品へ同梱） |
| ブラウザー画面（ローカルWebUI）で編集・生成・採用・ビルドする | [NovelAI WebUI（ポート8765）](../skills/novelai-batch-webui/SKILL.md)、[PixAI WebUI（ポート8775）](../skills/pixai-batch-webui/SKILL.md) | 利用者・エージェント共通（作品の `.agents/skills/` へ同梱） |
| 印刷する場合だけ入稿仕様を整理する | [印刷オプション](../templates/manga-project/PRINT-OPTION.md) | 印刷希望者向け（新規作品へ同梱・既定は無効） |

## 2. 作画手段・制作工程・エージェント向け実行手順

| 目的 | 参照先 | 対象読者・配布の扱い |
| --- | --- | --- |
| 工程と確認の順序、PNG確認からPSD引き渡しまでの流れ | [漫画制作のプロセス](knowledge/manga/08-workflow-review.md)、[PSD引き渡し](knowledge/psd-handoff.md) | エージェント・利用者共通（新規作品へ同梱） |
| 作画環境の選び方とOpus等の費用・一貫性ルール | [AIによる画像制作](knowledge/ai-production.md)、[コマ割り方針](knowledge/panel-layout-policy.md) | エージェント・利用者共通（新規作品へ同梱） |
| NovelAI APIでの接続・要求組み立て・一括生成・組版 | [NovelAI制作手順](../templates/manga-project/docs/knowledge/novelai-composed-production.md)、[NovelAI API接続手順](knowledge/novelai-api.md) | エージェント・利用者共通（新規作品へ同梱。画風見本 `resources/novelai-style-samples/index.html` はキット側を参照） |
| PixAI APIでの接続・モデル選択・要求組み立て・一括生成・組版 | [PixAI制作手順](../templates/manga-project/docs/knowledge/pixai-composed-production.md)、[PixAI API接続手順](knowledge/pixai-api.md) | エージェント・利用者共通（新規作品へ同梱。モデル・画風見本 `resources/pixai-model-samples/index.html` はキット側を参照） |
| 外部機能（ComfyUI / Qwen等）へ下絵・参照を渡しコマ別に作る | [共通手順](knowledge/external-panel-i2i.md)、[Qwen-Image 2.1](knowledge/image-generation/qwen-image-2.1.md)、[根拠と限界](knowledge/image-generation/production-evidence.md) | エージェント・利用者共通（新規作品へ同梱） |
| 知識・技法と記入雛形を選ぶ | [ノウハウ一覧](../templates/manga-project/docs/MANGA-KNOWHOW.md) | エージェント・利用者共通（新規作品へ同梱） |
| レビューの重点と共通知識・利用Skillを選ぶ | [レビュー運用](knowledge/review-workflow.md)、[人物・情報・読みやすさ・終幕](knowledge/review-workflow.md#common-knowledge) | エージェント向け（新規作品へ同梱） |
| 場面の笑い・魅力・感情・関係・展開を監修する | [監修知識の一覧](knowledge/supervision/README.md)、[監修スキル](../skills/manga-supervision/SKILL.md) | エージェント・利用者共通（マニフェスト掲載分を同梱） |
| 任意の日本語推敲スキル・必須工程チェッカー・動画試作を使う | [推敲スキル](knowledge/optional-skills.md)、[プロセスチェッカー](knowledge/process-checker.md)、[動画試作](knowledge/video-previsualization.md)・[動画補助処理](knowledge/video-tools.md) | 希望時のみ利用（新規作品へ手順を同梱） |

## 3. キットの構成・出典・保守・公開資料

| 目的 | 参照先 | 対象読者 |
| --- | --- | --- |
| 作品フォルダの作成仕組みと、コピーされるファイル／キット側参照の区別を確認する | [構成と配布](architecture.md) | 利用者・キット保守者 |
| 出典と取得日・適用範囲を確かめる | [出典台帳](SOURCES.md)、[脚本資料](knowledge/manga-sources.md) | 利用者・キット保守者 |
| ライセンスと第三者資料の扱いを確認する | [利用条件と第三者資料](RIGHTS.md) | 利用者・キット保守者 |
| このフォルダからGitへコミットする前に検証する | [公開手順](publication.md) | キット保守者 |
