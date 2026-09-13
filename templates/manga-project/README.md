# 漫画プロジェクト

作品名と配布元は `project.json`。まず `docs/story/BRIEF.md` に狙いを書き、`docs/PLAN.md` と `docs/PROGRESS.md` を更新する。

- 共通知識の入口: [制作運用](docs/knowledge/review-workflow.md)
- 記録依頼がある場合のフィードバック: [フィードバック手順](docs/knowledge/feedback-workflow.md)
- 環境設定: [セットアップ](docs/SETUP.md)
- 設定確認: `.\scripts\Resolve-ReviewProfile.ps1 -Preset 'daily'`
- 同梱キットの利用条件: [MIT License](docs/toolkit-license.txt)。この条件は制作する漫画や持ち込む素材へ自動適用しない。

作成時に案内された絶対パスのこの作品フォルダを開き、Codexの新しい会話で制作を開始する。配布元のキットからは開き直しが必要。ChatGPTのWindows用・Mac用アプリとVS Codeで開く方法は、Codexが案内する時点の最新公式情報を調べて説明する。[開き直しの案内](docs/knowledge/codex-operation.md#作品フォルダでcodexを開き直す)を参照する。この作品プロジェクトでは、キット内で例外制作するためのファイルは不要。

収録内容は [漫画制作のノウハウ一覧](docs/MANGA-KNOWHOW.md)（技法76項目、漫画の基礎、演出・比較手順、記入雛形）から選べる。漫画の字コンテからネーム・作画へ進み、まずPNGプレビューで確認・修正する。修正がなくなったらPSD作成の指示を確認し、指示がなければ作るか聞いて回答を待つ。既に指示があれば再確認せず、[PSDの条件](docs/knowledge/psd-handoff.md)を満たす原稿を作成・検証して人間へ渡す。原則、人間がCLIP STUDIO PAINTで仕上げて外部公開する。CBZは明示指定時だけ作成する。映画・ドラマは必要な場面の補助として参照する。
