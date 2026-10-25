# 漫画プロジェクト

ここは作成された個別作品のプロジェクトフォルダです。作成時に案内された絶対パスのこのフォルダをCodex（または指定したAIエージェント）で開き、**新しい会話**で漫画制作を始めます（配布元のキットからは開き直しが必要です）。

---

## 1. 最初の制作依頼（はじめ方）

キャラクター・あらすじ・ページ数を伝えると、追加設定なしでWeb公開用漫画の全ページをPNGプレビューまで制作します（画像生成・編集に使える環境が1つ必要です）。

> **最初の依頼文例：**
> 「女性2人が休日にゲームをする、最後にオチのある2ページ漫画を作ってください。まず利用できる画像生成手段を確認して、Web用PNGまで進めてください。PSDは不要です」

- **記録ファイルはAIが更新**：作品名と配布元は `project.json` に記録されています。制作開始時にAIエージェントが [OPTION.md](OPTION.md) を確認し、`docs/story/BRIEF.md`・`docs/PLAN.md`・`docs/PROGRESS.md` を作成・更新するため、人間が最初にすべてのファイルを手で埋める必要はありません。
- **好みを変えたいとき**：既定は右から左へ読む単ページ・白地です。変更したい項目がある場合だけ、[OPTION.md](OPTION.md) の「現在の設定」を編集するか会話で伝えてください（未記載はデフォルトを使用します）。
- **開き直し手順がわからないとき**：利用する環境（Windows／Mac、アプリ／VS Code）をCodexへ伝えると、最新公式情報を調べて出典URL・確認日付きで案内します。手順がわかる場合は返信せず、そのままこのフォルダを開いて構いません（[開き直しの案内](docs/knowledge/codex-operation.md#作品フォルダでcodexを開き直す)）。この作品プロジェクトでは、キット内で例外制作するためのファイルは不要です。

---

## 2. 作画手段別の準備と編集ガイド

使う作画手段に応じて、次の手順・ガイドを参照してください（すべてのサービスを設定する必要はありません）。

| 作画手段 | 概要・文字と枠の扱い | 参照ガイド（利用者向け／手順書） |
| --- | --- | --- |
| **内蔵 `imagegen`**<br>（利用可能なCodex環境） | 番号付きレイアウト画像と各コマの内容を渡し、**文字・フキダシ込みでページ全体を一括生成**するのが基本。生成画像の実寸に枠と最終PNGを合わせる | [コマ割りの手順](docs/knowledge/panel-layout-policy.md)、[基本枠の設定](docs/knowledge/page-layout.md) |
| **NovelAI API**<br>（コマ別生成＋組版） | 文字・枠なしの絵を生成し、後から `scripts/typeset_manga.py` 等で枠・フキダシ・縦書き文字を組版。APIキーは `.env` または `.secrets/novelai.env` に設定 | ・初回設定：[セットアップ](docs/SETUP.md)、[API接続手順](docs/knowledge/novelai-api.md)<br>・見た目変更：[キャラクター・絵柄・背景の編集と再生成](docs/novelai-prompts/README.md)<br>・画面操作：[NovelAI WebUI（ポート8765）](.agents/skills/novelai-batch-webui/SKILL.md)<br>・制作手順：[NovelAIでの制作手順](docs/knowledge/novelai-composed-production.md) |
| **PixAI API**<br>（コマ別生成＋組版） | 公式15モデルやLoRA等で文字・枠なしの絵を生成し、後から枠・フキダシ・縦書き文字を組版。APIキーは `.env` または `.secrets/pixai.env` に設定（生成にはクレジット消費の明示許可が必要） | ・初回設定：[セットアップ](docs/SETUP.md)、[PixAI API接続手順](docs/knowledge/pixai-api.md)<br>・見た目変更：[キャラクター・絵柄・背景・LoRAの編集と再生成](docs/pixai-prompts/README.md)<br>・画面操作：[PixAI WebUI（ポート8775）](.agents/skills/pixai-batch-webui/SKILL.md)<br>・制作手順：[PixAIでの制作手順](docs/knowledge/pixai-composed-production.md) |
| **外部生成・下絵参照i2i**<br>（ComfyUI / Qwen等） | 下絵やキャラ参照画像を渡してコマ別に作画し、後から枠・フキダシ・文字を組版 | [外部生成によるコマ作画](docs/knowledge/external-panel-i2i.md)、[Qwen-Image 2.1](docs/knowledge/image-generation/qwen-image-2.1.md) |

- **作品内に同梱されるファイルとキット側参照の区別**：共通知識・スキル・スクリプトはこの作品フォルダ内にコピーされていますが、**NovelAIの画風見本**（`resources/novelai-style-samples/index.html`）と**PixAIのモデル・画風見本**（`resources/pixai-model-samples/index.html`）は配布元キット側（`project.json` の `sourceKitRelativePath`）を参照します。

---

## 3. PNG確認・PSD引き渡し・印刷設定

- **まずPNGプレビューで確認・修正**：字コンテからネーム・作画へ進み、最初にPNGプレビューで確認・修正します。PNGの修正確認はユーザーの回答を待ちます。
- **希望時のみPSDを作成**：PNGに修正がなくなったらPSD作成の指示を確認し、指示がなければ作るか聞いて回答を待ちます。既に指示があれば再確認せず、[PSDの条件](docs/knowledge/psd-handoff.md)を満たす原稿を作成・検証して引き渡します（依頼例：「PNG確認後、絵・フキダシ・文字を分けたPSDも作って」）。
- **PSDのレイヤーと文字の扱い**：PSDは制作時に実際に分けて保持できた素材（NovelAI / PixAI組版での未加工原画、マスク付き配置画像、フキダシ、画像化した文字レイヤーなど）を格納します。`imagegen` で絵と文字を1枚に一体生成した画像が自動でパーツ別レイヤーや編集可能なテキストになるわけではありません。CLIP STUDIO PAINT等で文字を打ち直せるよう、確定した台詞原文も [セリフ原文と文字配置](docs/production/DIALOGUE.md) に保存して渡します。
- **仕上げ・公開・印刷設定**：原則として人間がCLIP STUDIO PAINTで仕上げて外部公開しますが、Web用PNGを受け取るだけの利用では必須ではありません。CBZは明示指定時だけ作成します。印刷専用の設定は [PRINT-OPTION.md](PRINT-OPTION.md) に分けており、Web制作では記入不要です。

---

## 4. 任意機能（必要な場合だけ利用）

- **場面ごとの監修（16テーマ）**：場面の笑い・魅力・感情・関係・展開の表現相談とPNG確認後の改善提案は [場面ごとの監修](docs/knowledge/supervision/README.md) と [監修記録](docs/reviews/SUPERVISION.md) を使います。
- **日本語推敲スキル**：[日本語推敲スキル](docs/knowledge/optional-skills.md)は [OPTION.md](OPTION.md) で選んだときだけ使います（既定は無効）。有効なら、この作品を開いた最初の作業時に自動導入します。`humanizer-jp` はGitを使用し、Gitがなければインストールしてよいか確認します。`japanese-natural-writing` はGeminiを使うため、環境があっても導入前に文章の送信・利用枠の消費を許可するか確認します。未回答・拒否の場合は導入を保留し、通常の漫画制作を続けられます。
- **自分用の必須工程の登録（プロセスチェッカー）**：次回から必須にしたい工程があれば、「字コンテ完成後の人物レビューを『指示』として登録して」などと伝えます。[プロセスチェッカー](docs/knowledge/process-checker.md)が内容・条件・確認時点・根拠・引継ぎ範囲を相談します。「指示」は工程報告時に照合し、「強く指示」は `AGENTS.md` にも反映し、必要ならHooksを追加します（「おまかせ」ならCodexが詳細を決めます）。新規配布時のリストは空で、空なら詳細な照合は行いません。次作品への引継ぎは元作品を明示した場合だけ行います。
- **フィードバック記録**：記録依頼がある場合のみ [フィードバック手順](docs/knowledge/feedback-workflow.md) に従って `docs/feedback/` に残します。

---

## 5. エージェント運用ルールと詳細資料

- **ブラウザー操作の禁止**：Codex等によるChrome・Edgeの起動・接続・操作と `chrome:control-chrome` の使用は禁止です。画像の確認には画像表示ツールを使い、ローカルWebUIや見本HTML等は案内されたURL・パスを人間が開きます。
- **制作ノウハウ一覧**：[漫画制作のノウハウ一覧](docs/MANGA-KNOWHOW.md)（技法78項目、漫画の基礎、演出・比較手順、記入雛形。映画・ドラマは必要な場面の補助として参照）
- **共通知識と利用Skillの対応**：[制作運用](docs/knowledge/review-workflow.md)・[汎用ノウハウ](docs/knowledge/review-workflow.md#common-knowledge)
- **レビュー設定の確認コマンド（任意）**：`.\scripts\Resolve-ReviewProfile.ps1 -Preset 'daily'`（Linuxは `bash scripts/Resolve-ReviewProfile.sh`）
- **同梱キットの利用条件**：[MIT License](docs/toolkit-license.txt)（この条件は制作する漫画や持ち込む素材へ自動適用されません）
