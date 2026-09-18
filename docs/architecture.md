# 構成と配布

このキットは保守・配布用で、通常の漫画制作はキット外に作る個別プロジェクトで行います。`templates/manga-project/` に直接作品を書き込まず、`scripts/New-MangaProject.ps1` で作品側へコピーします。キット内での制作には、ユーザーの明示指示と、ユーザー自身がルートに作成した `特別な理由でこのフォルダの中で漫画を作ります.txt` の確認が必要です。[例外手順](../README.md#どうしてもこのキット内で漫画を作る場合の例外)を参照してください。

## ファイルの役割

| 場所 | 用途 | 新規作品への配布 |
| --- | --- | --- |
| `docs/knowledge/manga/` | 漫画の工程・技法。人物・情報・演技・回収の汎用知識も該当項目へ統合 | 同じ相対パスへコピー |
| `docs/knowledge/` 直下 | 読みやすさ等の観点別詳細、共通レビュー、PSD・設定・操作などの運用手順 | 同じ相対パスへコピー |
| `docs/knowledge/supervision/` | ギャグの監修知識・利用手順 | 明示リストの文書とマニフェストを同梱 |
| `skills/` | 役割別スキルの原本 | `.agents/skills/` へコピー |
| `templates/manga-project/` | 作品設定・記録の雛形、コマ割りテンプレート素材 | 作品ルートへコピー |
| `templates/manga-project/OPTION.md` | 制作開始時に変更できる９項目の初期設定 | 作品ルートへコピー。適用手順は `docs/knowledge/project-options.md` |
| `scripts/New-MangaProject.ps1` | 新規作品の作成 | しない |
| `scripts/Resolve-ReviewProfile.ps1` | レビュー重点の解決 | `scripts/` へコピー |
| `scripts/validate_panel_plan.py` | コマ割り計画のルール検証 | `scripts/` へコピー |
| `scripts/build_panel_templates.py`・`scripts/render_panel_templates.cjs`・`scripts/check_panel_templates.py` | コマ枠素材の生成・検査（キット保守用） | しない |
| `scripts/video/` | 任意の動画生成・編集の補助 | 同じ相対パスへコピー |
| `tests/` | 配布と動画編集の検証 | しない |
| `examples/` | Gitで公開する作例PNGと説明 | しない |
| `backup/`、`.work/` | 非公開の退避と検証生成物 | 公開・配布とも対象外 |
| `特別な理由でこのフォルダの中で漫画を作ります.txt` | ユーザーが例外制作時だけ作成 | 公開・配布とも対象外 |

雛形、共通知識、スキルを別々に保守し、作成時に一つの作品へ組み立てます。作品は配布元への実行時依存を持ちません。版と各ファイルのSHA-256は `docs/distribution-snapshot.json`、作品名・作成日・配布版は `project.json` に記録します。保存する作業パスは相対パスです。

## 新規作品を作る

`manga-supervision` は版0.3.1ではギャグのみを監修し、字コンテの相談と画像レビューに使います。手順はスキル、知識は `docs/knowledge/supervision/gag/` に置きます。メインエージェントが採否を統合し、独立したエージェントの常時起動は要求しません。

汎用知識は用途の同じ既存文書へ統合し、通常のknowledgeとして配布します。[共通知識と利用Skillの対応](knowledge/review-workflow.md#common-knowledge)を入口に、用途とレビュー観点に沿って分類・統合します。監修知識だけは `docs/knowledge/supervision/distribution.json` の明示リストで制御し、通常のコピーから `supervision/` を除いて一度だけ組み込みます。監修文書を追加・変更する場合はリスト、許可するパス、`.gitignore` をそろえ、配布・公開テストを実行します。

リポジトリのルートから実行します。フォルダ名は固定していません。

```powershell
.\scripts\New-MangaProject.ps1 -ProjectName '作品名' -WhatIf
.\scripts\New-MangaProject.ps1 -ProjectName '作品名'
# 既存の親フォルダを相対パスで指定する場合
.\scripts\New-MangaProject.ps1 -ProjectName '別作品' -DestinationParent '..'
```

既定の作成先は `../作品名/`。`-DestinationParent` を変える場合も通常の制作先はキット外にします。日本語、英数字、空白、ハイフン、アンダースコアを使用できます。名前にパスやWindowsの予約名は使えません。既存フォルダは上書きせず、`-WhatIf` ではファイルを作りません。

成功時は作成先の絶対パスとCodexを開き直す案内を表示します。戻り値の `Path` は呼び出し元からの相対パス、`AbsolutePath` はユーザーへの表示用です。`project.json` と `docs/distribution-snapshot.json` に絶対パスは保存しません。Codexは実際の作成先を確認して返信にも絶対パスを示し、ChatGPTのWindows用・Mac用アプリとVS Codeの両方で開く手順を、案内時点の最新公式情報を調べて説明します。[開き直しの手順](knowledge/codex-operation.md#作品フォルダでcodexを開き直す)を参照してください。

作品側で新しいCodexの会話を開いてから制作を始めます。配布元の会話で作成先へ移動しただけでは、プロジェクトの切り替えが完了したとは扱いません。作品へ配る `AGENTS.md` は作品用のルールであり、キット用の例外ファイルを要求しません。

作成スクリプトは自身の位置を基準に原本を探します。内部では解決済みパスで配置先を確認しますが、特定のマシンやフォルダ名を埋め込みません。秘密情報に使われるファイル名、想定外の形式、リンクで配布元の外へ出る構成は配布前に拒否します。途中失敗時の部分フォルダは調査用に残ります。

## 更新とフィードバック

初回公開版は `0.1.0`。以降は `distribution-version.txt` を更新して配布します。既存作品は自動同期せず、必要な場合に作品側の変更と比較します。

`0.3.1` では汎用知識を `docs/knowledge/manga/` とknowledge直下の既存文書へ、ギャグ監修を `docs/knowledge/supervision/gag/` へ配置し、参照するスキルも統合先へそろえています。以前に作成した作品は、その作品内の配置とスキルの組み合わせで引き続き利用できます。既存作品を移行するときは、知識だけでなく参照するスキル・文書・配布記録も合わせて確認します。

作品側のフィードバック記録は、残してほしいと依頼された場合だけ行います。記録するかの質問や、毎回の還元候補づくりは行いません。通常の進捗・制作判断・納品検証は必要な範囲で継続します。[フィードバック手順](knowledge/feedback-workflow.md)を参照してください。
