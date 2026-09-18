# このフォルダからコミットする前の検証

初回公開版は `distribution-version.txt` で管理します。リポジトリ名や作業フォルダ名は固定していません。

このフォルダをそのままGitの作業ツリーとして使い、必要な変更をユーザーが直接コミットします。公開用ZIPや別の公開用フォルダは作りません。`scripts/public_release.py` はファイルを変更しない検査専用の処理です。

## 公開対象

汎用知識は `docs/knowledge/manga/` とknowledge直下の既存文書に統合し、通常のknowledgeとして公開・配布します。`docs/knowledge/supervision/` は、`docs/knowledge/supervision/distribution.json` に列挙した監修文書・出典台帳とマニフェストだけを対象にします。調査の図版・草案履歴・検証課題は `.work/` に残し、同梱しません。

README、作業ルール、共通知識、スキル、作品雛形、配布・動画補助スクリプト、テスト、`examples/` の公開用作例と説明を公開します。作例として指定したもの以外の入力原文、検討履歴、過去の版、素材、漫画・動画サンプル、ローカル環境情報、検証生成物は対象外です。

`examples/` では通常の文書・コード形式に加えてPNGを公開できます。新規作品プロジェクトには作例をコピーしません。コマ枠素材は `templates/manga-project/templates/panel-templates/` の `index.html`、`svg/`・`guides/` 直下のSVG、`png/`・`previews/` 直下のPNGだけを追加で許可し、作品へ配布します。別の場所の画像やHTMLを一括で許可しません。

公開するPNGはExif・テキスト・生成来歴・色プロファイル・解像度情報などの付加情報を除去します。公開検査では画像本体の `IHDR`・`PLTE`・`IDAT`・`IEND` と透明度の `tRNS` のみを許可し、その他のチャンクや末尾の余分なデータがあればエラーにします。画像本体は再圧縮せず保持し、寸法・画素データの一致を確認します。SVG・HTML・JSONも、作品名・セリフ・個人情報・ローカルパスなどを含まない汎用素材であることを確認します。

`backup/` と `.work/` はGitのコミット対象から除外します。ローカル作業用の `docs/PLAN.md` と `docs/PROGRESS.md` も公開しません。作品に配る同名の雛形は公開対象です。ユーザーが例外制作のために作る `特別な理由でこのフォルダの中で漫画を作ります.txt` はGit・新規作品への配布に含めません。例外制作時の素材・原稿も `.work/` などの非公開領域へ置きます。

`.gitignore` は公開する場所と文書・コード・作例PNGの形式を限定し、公開フォルダ内のバックアップ、素材・出力用フォルダ、キャッシュ、秘密設定も除外します。`templates/` は `manga-project/` だけを対象にします。公開可能な形式の文書に書かれた私的な内容までは判別できないため、公開前に差分も確認します。

`.gitignore` は追跡済みファイルや過去のコミットには適用されず、`git add -f` による強制追加も防ぎません。バックアップや作業物はルートの `backup/`・`.work/` に保存し、公開フォルダ内へ置かないでください。

## 手元で確認する

```powershell
python .\scripts\public_release.py check
python .\scripts\check_panel_templates.py
.\tests\Test-Scaffold.ps1
python -X utf8 -m unittest discover -s tests -p 'test_*.py'
```

公開検査は公開対象だけを読み、作業用の絶対パス、固定フォルダ名、ローカルリンク、許可しない形式や秘密情報らしい内容を確認します。外部URLは作業パスとして扱いません。動画編集テストはffmpeg・ffprobeがある場合に実行します。

Windowsでも日本語を含む検証記録を読めるよう、Pythonの全体テストは `-X utf8` を付けて実行します。

コマ枠素材を変更したときだけ、キットで `python scripts/build_panel_templates.py`、`node scripts/render_panel_templates.cjs --all` の順に再生成します。後者にはNode.js・Playwrightと対応ブラウザーが必要です。生成処理は作品設定JSONを上書きしません。通常の作品制作では同梱素材を使います。

## Gitの差分を確認してコミットする

このフォルダのルートで、追加候補と変更内容を確認します。

```powershell
git status --short
git diff --check
git diff
git ls-files --cached --others --exclude-standard
git ls-files --cached --ignored --exclude-standard
```

最後のコマンドは、除外対象なのに追跡されているファイルがないことを確認するためのもので、出力が空になることを確認します。公開検査は作業ツリーを読むため、Gitへ追加するファイルやステージした内容は別途確認します。

ユーザーがコミットしたい変更をステージしたら、次のコマンドまたはGitの画面で内容を確認し、そのままこのフォルダからコミットします。作例は `examples/README.md` とメタ情報除去済みのPNGを含めます。

```powershell
git diff --cached --name-status
git diff --cached --check
git diff --cached
```

Codexによるコミット、GitHubでのリポジトリ作成、リモート設定、push、リリース登録は、それぞれ操作を依頼された場合に行います。独自作成部分はMITで公開します。[第三者資料の扱い](RIGHTS.md)も確認してください。
