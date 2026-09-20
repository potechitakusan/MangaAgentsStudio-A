# 漫画プロジェクト

キャラ・あらすじ・ページ数を伝えると、追加設定なしでWeb用漫画の全ページをPNGまで制作する。既定は右から左へ読む単ページ、白地。１ページ全体を生成する場合、使用ツールの生成画像の実寸に枠を合わせ、同じ寸法でPNGを書き出す。生成・枠配置・最終PNGの寸法はOPTIONで個別に指定できる。画像生成・編集に使える環境が必要。例：「キャラは○○と△△、あらすじは□□。8ページでインターネット公開用の漫画を作って」。PNGの修正確認はユーザーの回答を待つ。

作品名と配布元は `project.json`。制作開始時に [OPTION.md](OPTION.md) を反映し、`docs/story/BRIEF.md` に狙いを書き、`docs/PLAN.md` と `docs/PROGRESS.md` を更新する。変更したい設定はOPTIONの「現在の設定」を編集するか会話で伝える。未記載はデフォルトを使い、開始後の編集は意図を確認してから反映する。印刷専用の設定は [PRINT-OPTION.md](PRINT-OPTION.md) に分けており、Web制作では記入不要。

余白や補助線は [基本枠の設定](docs/knowledge/page-layout.md)、文字設定は [セリフ原文と文字配置](docs/production/DIALOGUE.md) を参照。PSDの依頼例は「PNG確認後、絵・フキダシ・文字を分けたPSDも作って」。画像化された文字は文字列として再編集できるとは限らないため、台詞原文も渡す。

[日本語推敲スキル](docs/knowledge/optional-skills.md)はOPTIONで選んだときだけ使う。有効なら、この作品を開いたCodexの最初の作業時に自動導入する。`humanizer-jp` はGitを使用し、Gitがなければインストールしてよいか確認する。`japanese-natural-writing` はGeminiを使うため、環境があっても導入前に文章の送信・利用枠の消費を許可するか確認する。未回答・拒否の場合は導入を保留し、通常の漫画制作は続けられる。

- 共通知識の入口: [制作運用](docs/knowledge/review-workflow.md)
- 共通知識と利用Skillの対応: [汎用ノウハウ](docs/knowledge/review-workflow.md#common-knowledge)
- 場面の笑い・魅力・感情・関係・展開の表現相談と画像レビュー: [場面ごとの監修](docs/knowledge/supervision/README.md)、[監修記録](docs/reviews/SUPERVISION.md)
- 記録依頼がある場合のフィードバック: [フィードバック手順](docs/knowledge/feedback-workflow.md)
- 環境設定: [セットアップ](docs/SETUP.md)
- 設定確認: `.\scripts\Resolve-ReviewProfile.ps1 -Preset 'daily'`
- 同梱キットの利用条件: [MIT License](docs/toolkit-license.txt)。この条件は制作する漫画や持ち込む素材へ自動適用しない。

作成時に案内された絶対パスのこの作品フォルダを開き、Codexの新しい会話で制作を開始する。配布元のキットからは開き直しが必要。やり方がわからない場合は、利用する環境（Windows／Mac、アプリ／VS Code）をCodexへ伝える。手順を求められた場合だけ、Codexは利用環境に合う最新の公式情報を調べ、出典URLと確認日を付けて説明する。手順がわかる場合は返信せず、そのままこの作品フォルダを開いてよい。[開き直しの案内](docs/knowledge/codex-operation.md#作品フォルダでcodexを開き直す)を参照する。この作品プロジェクトでは、キット内で例外制作するためのファイルは不要。

収録内容は [漫画制作のノウハウ一覧](docs/MANGA-KNOWHOW.md)（技法77項目、漫画の基礎、演出・比較手順、記入雛形）から選べる。漫画の字コンテからネーム・作画へ進み、まずPNGプレビューで確認・修正する。修正がなくなったらPSD作成の指示を確認し、指示がなければ作るか聞いて回答を待つ。既に指示があれば再確認せず、[PSDの条件](docs/knowledge/psd-handoff.md)を満たす原稿を作成・検証して人間へ渡す。原則、人間がCLIP STUDIO PAINTで仕上げて外部公開する。CBZは明示指定時だけ作成する。映画・ドラマは必要な場面の補助として参照する。
