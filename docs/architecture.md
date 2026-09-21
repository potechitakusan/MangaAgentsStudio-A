# 構成と配布

このキットは保守・配布用で、通常の漫画制作はキット外に作る個別プロジェクトで行います。`templates/manga-project/` に直接作品を書き込まず、`scripts/New-MangaProject.ps1` で作品側へコピーします。キット内での制作には、ユーザーの明示指示と、ユーザー自身がルートに作成した `特別な理由でこのフォルダの中で漫画を作ります.txt` の確認が必要です。[例外手順](../README.md#どうしてもこのキット内で漫画を作る場合の例外)を参照してください。

## ファイルの役割

| 場所 | 用途 | 新規作品への配布 |
| --- | --- | --- |
| `docs/knowledge/manga/` | 漫画の工程・技法。人物・情報・演技・回収の汎用知識も該当項目へ統合 | 同じ相対パスへコピー |
| `docs/knowledge/` 直下 | 読みやすさ等の観点別詳細、共通レビュー、PSD・設定・操作などの運用手順 | 同じ相対パスへコピー |
| `docs/knowledge/supervision/` | 場面ごとの監修知識・出典・利用手順 | 明示リストの文書とマニフェストを同梱 |
| `skills/` | 役割別スキルの原本 | `.agents/skills/` へコピー |
| `templates/manga-project/` | 作品設定・記録の雛形、コマ割りテンプレート素材 | 作品ルートへコピー |
| `resources/novelai-style-samples/` | NovelAI画風候補のキット専用閲覧見本 | キットにのみ同梱。新規作品へコピーしない |
| `templates/manga-project/OPTION.md` | Web制作を基本とする、用途・好みで選べる初期設定 | 作品ルートへコピー。適用手順は `docs/knowledge/project-options.md` |
| `templates/manga-project/PRINT-OPTION.md` | 印刷を選んだ場合だけ使う設定・仕様・検証記録 | 作品ルートへコピー。既定は使用しない |
| `templates/manga-project/config/page-layout.json` | 生成希望・枠配置・最終PNGの寸法、余白・線幅の換算基準と固定指定 | 同じ相対パスへコピー。版2は生成実寸に合わせる。版1の固定寸法も配置処理で読める |
| `templates/manga-project/config/optional-skills.json` | 任意の推敲スキルの取得先・固定版・ファイルハッシュ | 同じ相対パスへコピー。第三者の本文は含めない |
| `templates/manga-project/config/process-requirements.json` | 個人の必須事項の空の雛形 | 空配列だけを配布。明示された作品からの引継ぎは作成時に別処理 |
| `scripts/process_checker.py` | 必須事項の登録・根拠管理・強い指示のAGENTS反映・任意のHooks | `scripts/` へコピー |
| `templates/manga-project/scripts/novelai_api.py` | 作品単位のNovelAIキー読込・生成なしの契約照会・明示実行による１枚生成 | 雛形から `scripts/` へコピー。Python標準ライブラリのみ。認証情報は配布しない |
| `templates/manga-project/config/novelai-request.example.json` | モデルとプロンプト未設定の生成要求例 | 同じ相対パスへコピー。採用後は作品側で要求JSONを作る |
| `scripts/New-MangaProject.ps1` | 新規作品の作成 | しない |
| `scripts/Resolve-ReviewProfile.ps1` | レビュー重点の解決 | `scripts/` へコピー |
| `scripts/Initialize-OptionalSkills.ps1` | 有効にした推敲スキルを作品の最初の作業時に導入。Gemini版は利用許可後のみ | `scripts/` へコピー。作品の作成時には実行しない |
| `scripts/validate_panel_plan.py` | コマ割り計画のルール検証 | `scripts/` へコピー |
| `scripts/prepare_page_layout.py` | 生成PNGの実寸または指定寸法に合わせ、枠・余白・線幅を換算。寸法の関係を記録しガイドは別出力 | `scripts/` へコピー。Python標準ライブラリのみ。画像生成・拡縮・最終PNG保存は制作工程で別途行う |
| `scripts/build_panel_templates.py`・`scripts/render_panel_templates.cjs`・`scripts/check_panel_templates.py` | コマ枠素材の生成・検査（キット保守用） | しない |
| `scripts/video/` | 任意の動画生成・編集の補助 | 同じ相対パスへコピー |
| `tests/` | 配布と動画編集の検証 | しない |
| `examples/` | Gitで公開する作例PNGと説明 | しない |
| `backup/`、`.work/` | 非公開の退避と検証生成物 | 公開・配布とも対象外 |
| `特別な理由でこのフォルダの中で漫画を作ります.txt` | ユーザーが例外制作時だけ作成 | 公開・配布とも対象外 |

雛形、共通知識、スキルを別々に保守し、作成時に一つの作品へ組み立てます。制作の共通知識とスクリプトは作品内に同梱し、NovelAIの画風見本を案内するときはキット側のHTMLの場所を使います。版と各ファイルのSHA-256は `docs/distribution-snapshot.json`、作品名・作成日・配布版・コピー元は `project.json` に記録します。コピー元の `sourceKitRelativePath` は作品ルートからキットへの相対パスで、作成スクリプトが実際の位置から算出します。見本案内時はこれを解決し、設定の `kit_sample_library_relative_path` を結合して実在だけを確認します。移動後に見つからない場合や記録のない既存作品では場所を確認し、パスを推測しません。保存する作業パスは相対パスです。

## 新規作品を作る

`manga-supervision` は版0.3.2では既存のギャグと、追加15テーマの試行版を扱い、字コンテの相談と画像レビューに使います。手順はスキル、知識は `docs/knowledge/supervision/` のテーマ別文書、追加15テーマの出典は同フォルダの `sources.md` に置きます。メインエージェントが採否を統合し、独立したエージェントの常時起動は要求しません。

汎用知識は用途の同じ既存文書へ統合し、通常のknowledgeとして配布します。[共通知識と利用Skillの対応](knowledge/review-workflow.md#common-knowledge)を入口に、用途とレビュー観点に沿って分類・統合します。監修知識だけは `docs/knowledge/supervision/distribution.json` の明示リストで制御し、通常のコピーから `supervision/` を除いて一度だけ組み込みます。監修文書を追加・変更する場合はリスト、許可するパス、`.gitignore` をそろえます。配布・公開テストは修正のたびに行わず、ユーザーからCommit前のチェックを依頼されたときに、[公開手順](publication.md)に従って実施対象と範囲を確認してから実行します。

リポジトリのルートから実行します。フォルダ名は固定していません。

```powershell
.\scripts\New-MangaProject.ps1 -ProjectName '作品名' -WhatIf
.\scripts\New-MangaProject.ps1 -ProjectName '作品名'
# 既存の親フォルダを相対パスで指定する場合
.\scripts\New-MangaProject.ps1 -ProjectName '別作品' -DestinationParent '..'
```

既定の作成先は `../作品名/`。`-DestinationParent` を変える場合も通常の制作先はキット外にします。日本語、英数字、空白、ハイフン、アンダースコアを使用できます。名前にパスやWindowsの予約名は使えません。既存フォルダは上書きせず、`-WhatIf` ではファイルを作りません。

成功時は作成先の絶対パスとCodexを開き直す案内を表示します。戻り値の `Path` は呼び出し元からの相対パス、`AbsolutePath` はユーザーへの表示用です。`project.json` と `docs/distribution-snapshot.json` に絶対パスは保存しません。Codexは実際の作成先を確認して返信にクリック可能なMarkdownリンクと、同じ絶対パスをそのままコピーできる文字列を併記し、「やり方がわからない場合は、ご利用の環境（Windows／Mac、アプリ／VS Code）を教えてください。必要な手順をご案内します」と添えます。作成のたびに操作手順を調べることはせず、手順を求められた場合だけ、利用環境に合う最新公式情報を検索・閲覧し、出典URLと確認日を付けて説明します。[開き直しの案内](knowledge/codex-operation.md#作品フォルダでcodexを開き直す)を参照してください。

作品側で新しいCodexの会話を開いてから制作を始めます。配布元の会話で作成先へ移動しただけでは、プロジェクトの切り替えが完了したとは扱いません。作品へ配る `AGENTS.md` は作品用のルールであり、キット用の例外ファイルを要求しません。

作成スクリプトは自身の位置を基準に原本を探します。内部では解決済みパスで配置先を確認しますが、特定のマシンやフォルダ名を埋め込みません。秘密情報に使われるファイル名、想定外の形式、リンクで配布元の外へ出る構成は配布前に拒否します。途中失敗時の部分フォルダは調査用に残ります。

## 個人の必須工程

[プロセスチェッカー](knowledge/process-checker.md)は `skills/manga-process-checker/` の手順と作品内の `config/process-requirements.json` を使います。標準工程の正本は既存の `docs/knowledge/manga/08-workflow-review.md` を参照し、重複して保守しません。ユーザーから登録を依頼された事項だけを追加し、０件なら詳細な照合は行いません。

保存先は作品内です。再開時は同じ正本と `.work/process-checker/` の記録を読みます。新規作成時の `-ProcessRequirementsFrom` がある場合だけ、指定された元作品の `carryForward: true` の指示をコピーします。強い指示は新しいAGENTS.mdへ反映し、変更された２ファイルの実際のハッシュを作成時の配布記録へ残します。引継ぎ元は `project.json` の `processRequirementsSourceRelativePath` に相対パスで保存します。

元作品の実施記録・素材・Hooks設定・信頼・外部利用の許可はコピーしません。Hooksの希望は指示として保持し、新しい環境で別途設定・レビューします。引継ぎ元未指定の新規作品は空のリストで始まります。既存作品への自動移行や、作品同士・ユーザー全体の設定との同期は行いません。配布雛形へ個人の指示・照合記録・Hooksが混入した場合は作成・公開の検査で拒否します。空の正本はキットでGit管理し、新規作成時に作品側の `.gitignore` へ個人の正本の除外を追記します。この `.gitignore` も変更後のハッシュを記録します。

## 更新とフィードバック

初回公開版は `0.1.0`。以降は `distribution-version.txt` を更新して配布します。既存作品は自動同期せず、必要な場合に作品側の変更と比較します。

`0.3.1` では汎用知識を `docs/knowledge/manga/` とknowledge直下の既存文書へ、ギャグ監修を `docs/knowledge/supervision/gag/` へ配置しました。`0.3.2` では 場面監修15テーマと出典台帳を同梱します。テーマの一覧は `docs/knowledge/supervision/README.md`、許可するファイルは `distribution.json` にまとめます。以前に作成した作品は、その作品内の配置とスキルの組み合わせで引き続き利用できます。既存作品を移行するときは、知識だけでなく参照するスキル・文書・配布記録も合わせて確認します。

作品側のフィードバック記録は、残してほしいと依頼された場合だけ行います。記録するかの質問や、毎回の還元候補づくりは行いません。通常の進捗・制作判断・納品検証は必要な範囲で継続します。[フィードバック手順](knowledge/feedback-workflow.md)を参照してください。
