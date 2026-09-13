# 公開用ファイルの書き出しと検証

初回公開版は `distribution-version.txt` で管理します。リポジトリ名や作業フォルダ名は固定していません。

## 公開対象

README、作業ルール、共通知識、スキル、作品雛形、配布・動画補助スクリプト、テストを公開します。入力原文、検討履歴、過去の版、素材、漫画・動画サンプル、ローカル環境情報、検証生成物は対象外です。

`backup/` と `.work/` はGitとアーカイブから除外します。ローカル作業用の `docs/PLAN.md` と `docs/PROGRESS.md` も公開しません。作品に配る同名の雛形は公開対象です。

`.gitignore` は公開する場所と文書・コードの形式を限定し、公開フォルダ内のバックアップ、素材・出力用フォルダ、キャッシュ、秘密設定も除外します。`templates/` は `manga-project/` だけを対象にします。公開可能な形式の文書に書かれた私的な内容までは判別できないため、公開前に差分も確認します。

`.gitignore` は追跡済みファイルや過去のコミットには適用されず、`git add -f` による強制追加も防ぎません。Git初期化後は次のコマンドで追加候補、除外対象なのに追跡されているファイル、ステージ済みの変更を確認します。2つ目の出力は空であることを確認してください。

```powershell
git ls-files --cached --others --exclude-standard
git ls-files --cached --ignored --exclude-standard
git diff --cached --name-status
```

フォルダを丸ごと手作業でZIP化しても `.gitignore` は適用されません。下記の書き出し処理は独自の公開範囲で検証するため、バックアップや作業物はルートの `backup/`・`.work/` に保存し、公開フォルダ内へ置かないでください。

## 手元で確認する

```powershell
python .\scripts\public_release.py check
.\tests\Test-Scaffold.ps1
python -m unittest discover -s tests -p 'test_*.py'
```

公開検査は公開対象だけを読み、作業用の絶対パス、固定フォルダ名、ローカルリンク、許可しない形式や秘密情報らしい内容を確認します。外部URLは作業パスとして扱いません。動画編集テストはffmpeg・ffprobeがある場合に実行します。

## 公開用の一式を作る

```powershell
python .\scripts\public_release.py export --output .\.work\public-release
```

検査に合格した公開対象だけを指定先へコピーし、同名のZIPを作ります。既存の出力フォルダ・ZIPは上書きしません。書き出し結果を公開内容の確認に使えます。

GitHubでのリポジトリ作成、リモート設定、コミット、push、リリース登録は別操作です。独自作成部分はMITで公開します。[第三者資料の扱い](RIGHTS.md)も確認してください。
