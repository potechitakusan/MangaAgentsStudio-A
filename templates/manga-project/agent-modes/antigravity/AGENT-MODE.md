# Antigravity用モードの読み替え

この作品は `New-MangaProject.ps1 -AgentMode Antigravity` または `New-MangaProject.sh --agent-mode Antigravity` で作成した。`project.json` の `agentMode` が `Antigravity` の作品でだけ適用する。共通ルールは `AGENTS.md` を正本とし、Codex固有の箇所は以下のとおり読み替える。ここにない規則はそのまま適用する。

## 呼称・開始・再開

- 文書中の「Codex」は、この作品を担当するAntigravityのエージェントを指す。開き直しの案内は「このフォルダでAntigravityを開き直してください」とする。
- 確認者・採用者には実際のモデル名を記録する。不明なら「Antigravity（モデル名未確認）」とし、推測で版を埋めない。
- `AGENTS.md`、このファイル、`project.json`、`docs/PROGRESS.md`、`docs/PLAN.md`、`OPTION.md` を確認してから工程を再開する。進捗・計画・採用記録は作品内に保存し、Antigravity側のArtifactsだけに残さない。
- LinuxではBash入口、WindowsではPowerShell入口を使う。初回・再開時の任意スキル確認は、Linuxなら `bash scripts/Initialize-OptionalSkills.sh`、Windowsなら `scripts/Initialize-OptionalSkills.ps1`。レビュー重点の解決も同じOSに対応する入口を使う。
- `wait_agent` 等のCodex固有ツールをあるものとして使わない。委任が必要なら実際の環境の手順を使い、メインが判断を統合する。

## 作画・組版

- Codexのimagegenが利用できる前提を置かない。作画前に、このセッションで利用可能な生成・編集・画像表示機能、採用モデル、入力方式を確認する。Geminiというモデル名だけで画像生成機能があると判断しない。
- 既定はNovelAIによるコマ別の素材生成と別組版。`docs/knowledge/novelai-composed-production.md`、`config/novelai-production-policy.json`、`scripts/novelai_batch.py` に従う。キー・画風・費用・使用枠の確認、人物試作、要求JSON、採用候補、作画後の照合、ページ組み直しを省略しない。
- ユーザーが別の生成環境や素材を指定した場合はその手順に従う。imagegen専用のページ一括生成・画像内文字生成の規則を他の環境へ一律適用せず、文字・吹き出しは共通方針どおり作画後に別に載せる。
- 生成手段や必要な設定がそろわない場合は作画を保留し、必要な設定を案内する。企画・字コンテ・ネーム等は進めてよい。コードで描いた絵を代替の完成原稿にしない。
- 画像編集が利用できない場合は再生成・配置変更・計画の見直しで対応し、未解決の問題はPNG提示時に伝える。

## 画像確認・ブラウザー・通信

- 候補・採用画像・完成ページPNGを、実際の画像表示機能で開いて確認する。パスの存在・画像寸法・生成ログだけで目視済みの照合表を書かない。
- 画像を表示できない場合は目視確認を未実施として扱い、PNGのパスを提示してユーザーの確認を求める。画像を開くためにブラウザーを起動しない。
- Chrome・Edgeの起動・接続・操作の禁止はAntigravityにも適用する。内蔵ブラウザー、ブラウザー用エージェント、Playwright・Selenium・CDP・ヘッドレス実行、既定ブラウザー経由も使わない。資料調査はブラウザー操作を伴わない検索・取得を使う。HTML等はパス・URLを提示してユーザーが開く。
- 通信・コマンドが権限やサンドボックスで拒否された場合はその環境の許可手順に従う。権限設定を勝手に変えたり、失敗だけでキーの再設定を求めたりしない。作成先はキット外のため、許可された作業範囲も確認する。

## スキル・任意の日本語推敲

- 制作スキルは作品の `.agents/skills/` を使う。`.agent/skills/` へ二重にコピーせず、ユーザー全体の保存先も使わない。必要な工程の `SKILL.md` を実際に読み、認識されない場合も同じ正本を参照する。
- 任意の日本語推敲は既定で無効。無効なら導入済みでも使わず、有効な場合も選択したスキルと対象だけに明示適用する。`agents/openai.yaml` の暗黙呼び出し無効化がAntigravityで効くとは仮定しない。
- Antigravityで制作していることを、任意のGemini推敲スキルの導入・追加呼び出しの許可とみなさない。導入前の許可、固定版照合、作品ごとの承諾記録は `docs/knowledge/optional-skills.md` のとおり。
- 第三者スキルがCodex照合や特定のCLI・モデルを要求する場合は、実行契約を読む。Gemini自身の照合・別CLI・別APIへ黙って変更しない。環境がそろわない推敲だけを保留して、通常の制作を続ける。

## 適用範囲と出典

2026-10-03確認。公式資料での仕様確認と、このキットの制作提案を区別する。

- [Rules](https://www.antigravity.google/docs/rules/)：`AGENTS.md`・`GEMINI.md` の認識と `@[label](path)` による本文展開。通常の `@filename` は本文展開ではない。
- [Agent skills](https://www.antigravity.google/docs/skills?tab=ide)：作品内の `.agents/skills/` と `SKILL.md` の認識。
- 上記の作画・許可・記録の読み替えはキットの運用方針。Antigravity実機での読込・画像表示・生成・任意スキルの実行は未検証。Linux入口についての既存のDebian動作確認と、Antigravity対応の動作確認を分ける。
