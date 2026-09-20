# 最初の環境設定

作品での初回作業時はOPTIONの日本語推敲スキル設定を解決し、`scripts/Initialize-OptionalSkills.ps1` を実行する。有効時だけ作品の `.agents/skills/` へ導入する。Gitがない場合はインストールの可否を確認し、Gemini版は利用可能な環境があっても利用枠の消費許可を必ず得てから導入する。未回答・拒否では通常の制作を続ける。[初回導入の手順](knowledge/optional-skills.md)を参照。

配布元のキットから、作成時に表示された絶対パスの作品フォルダへCodexを開き直してから設定する。やり方がわからない場合は、利用する環境（Windows／Mac、アプリ／VS Code）をCodexへ伝える。手順を求められた場合だけ、Codexが[開き直しの案内](knowledge/codex-operation.md#作品フォルダでcodexを開き直す)に沿って、利用環境に合う最新公式情報を調べて説明する。現在の作業フォルダにこの作品の `project.json` と `AGENTS.md` があることを確認する。

作品名はproject.jsonに記録される。config/review-profiles.jsonのdefaultsを作品に合わせ、必要なシーンをscenesへ追加する。解決例と意味はknowledge/review-workflow.md。

input/に作品固有の入力、assets/characters/にキャラ参照、assets/references/に背景などの参照、workflows/にComfyUIワークフロー、output/に生成物を置く。指示・採否・検証結果はdocs/に残す。

画像制作時にローカルのComfyUIへの相対パス・GPU・モデル・版・起動手順を確認し、秘密値を除いてdocs/experiments/へ記録する。既存環境の起動許可はその作品でのユーザー指示に従う。モデルやLoRAを自動インストールする初期処理はない。

動画で映画的演出を試す依頼には、任意機能のmanga-video-previsualization Skillと [動画試作の運用](knowledge/video-previsualization.md) を使う。動作確認済みの動画ワークフローを作品のworkflows/へ用意し、モデルと入力の対応を確認してから実行する。人物参照はassets/characters/、動画・音声はoutput/、条件・所要時間・採否はdocs/experiments/へ保存する。通常の漫画制作の前提作業にはしない。

NovelAIを使用する際は、作品内の.secrets/（スクリプトが作成する空フォルダ）または環境変数に認証情報を用意する。.env.exampleは項目名の例であり、キーの自動読込やAPI接続はまだ実装されていない。実行前に公式仕様と利用可能な枠を確認する。有効なOpus契約なら [Anlasを消費しない生成条件](knowledge/ai-production.md#novelai-opus)を確認し、１回１枚・28ステップ以下（V5は初期値23、V4.5以前は28）を基準にする。生成寸法は使用ツールに合わせる共通の [ページ設定](knowledge/page-layout.md)に従う。採用寸法・モデルと追加機能を含めた0 Anlasの確認、V5の利用上限の残量確認も行う。

新しいCodexセッションで作品ルートを開き、AGENTS.mdとローカルSkillsが認識されていることを確認する。配布したSkillsはこのプロジェクトの共通知識と組み合わせて使う。

[ノウハウ一覧](MANGA-KNOWHOW.md)から必要な知識を選ぶ。まずPNGプレビューで確認・修正し、修正がなくなってからPSD作成へ進む。PSD作成の指示がなければ作るか聞いて回答を待ち、既に指示があれば再確認しない。後でPSDにできるよう分離素材とセリフ原文を保持する。PSD作成に進む際は作成・再読込の手段と、CLIP STUDIO PAINTで確認できる環境を調べ、PNGの確認結果・PSD作成指示・仕様を[引き継ぎ記録](production/PSD-HANDOFF.md)へ残す。依頼されたPSDは作成・検証して人間に引き渡す。人間が仕上げ・公開する。CBZは明示指定時だけ作成する。
