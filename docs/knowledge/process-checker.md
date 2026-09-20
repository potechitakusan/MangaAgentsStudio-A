# プロセスチェッカーの登録・照合・引き継ぎ

更新・公式情報確認日：2026-09-21。このキット独自の運用。実行漏れが完全になくなると保証するものではなく、実際の会話・再開・修正での効果は別途検証する。

## 使い方と範囲

漫画の制作を経験したユーザーが「今後これを必須にしたい」と指示したとき、`manga-process-checker` で追加方法を相談する。登録の依頼がない制作・修正では、候補づくりや毎回の登録質問を行わない。通常のフィードバック記録とは別の、明示依頼に基づく作品設定である。

| レベル | 使い方 | 反映先 |
| --- | --- | --- |
| 指示 | 字コンテ完了・ページ完成等の報告時に実施を照合し、不足があれば対応を返す | 必須事項ファイルと照合記録 |
| 強く指示 | 報告時の照合に加え、指定した時点での実施をAGENTS.mdに明記する。必要なら報告忘れをHooksで補う | 必須事項ファイル、AGENTS.mdの管理区間、相談して選んだHooks |

どちらもユーザーが必須にした事項。「指示」は任意という意味ではない。適用条件に合わない事項は理由を記して対象外にできるが、Codexの好みで免除・格下げ・削除しない。指示の変更・解除はユーザーの明示指示から行う。

登録時は、行為・条件・適用開始・レベル・対象単位・期限・実施の根拠・次作品への引継ぎ可否・反映先を相談する。「次から」はこれからの作業や改稿に適用し、過去の成果物にも適用する場合は範囲を相談する。「おまかせ」ならその範囲をCodexが決め、根拠を説明して記録する。Hooksの信頼操作まで自動承認したことにはしない。

## ファイルの役割

| 場所（作品ルート基準） | 役割 |
| --- | --- |
| `docs/knowledge/manga/08-workflow-review.md` | 標準プロセス全体の正本。必須事項だけを絞って照合するための参照 |
| `config/process-requirements.json` | ユーザーの必須事項の正本。新規配布時は空配列 |
| `.work/process-checker/` | 相談の原文、登録前後、報告入力、実施記録、Hooks設定前の退避。作品内だけで保持 |
| `AGENTS.md` の `process-checker:strong` 管理区間 | 「強く指示」を正本から反映した実行指示。管理区間外は保持 |
| `.codex/hooks.json` | 希望したときだけ作るHooks。他のHooksを保持して追加 |
| `scripts/process_checker.py` | 登録、相対パス・状態・根拠ハッシュの管理、明示的な引継ぎ、Hooksの設定と応答 |

個人用の指示をキットや共通雛形へ還元しない。ユーザー全体のフォルダには保存しない。作品の指示ファイル・`.work/`・Hooksは作品用 `.gitignore` で除外する。強い指示を含んだAGENTS.mdを作品側で公開する場合は、個人設定の管理区間も確認する。キットの配布元では空の正本だけを保守する。

## コマンドと登録形式

Python 3.10以上、標準ライブラリだけを使う。作品ルートからの例。ユーザーにJSONやコマンドを手入力させず、Codexが相談内容を反映して実行する。

```powershell
python -X utf8 scripts/process_checker.py status
python -X utf8 scripts/process_checker.py checkpoints
python -X utf8 scripts/process_checker.py add --input .work/process-checker/request.json
python -X utf8 scripts/process_checker.py replace --input .work/process-checker/replacement.json
python -X utf8 scripts/process_checker.py remove --id proc-example --decision-note 'ユーザーの解除指示の要約'
```

登録例（この例を既定の指示として追加しない）：

```json
{
  "id": "proc-script-review",
  "level": "指示",
  "instruction": "字コンテ完成後に人物の目的と行動の整合をレビューする",
  "checkpoint": "script-complete",
  "scope": "project",
  "condition": "登録後にこの作品で字コンテを作成または内容を修正したとき",
  "completionCriteria": "対象版を明記したレビューと指摘への対応方針がある",
  "carryForward": true,
  "enforcement": "report",
  "decision": "相談済み",
  "decisionNote": "ユーザーが内容・レベル・確認時点と次作品への引継ぎを指定"
}
```

- `id`：変更・報告・解除に使う固定ID。`add` では省略時に採番する。
- `level`：「指示」「強く指示」の２択。未指定なら相談し、「おまかせ」の場合だけCodexが選ぶ。
- `scope`：`project` は作品全体、`page` は各ページ。章などが必要な場合は現行の対応範囲を説明し、対象の扱いを相談する。
- `condition`／`completionCriteria`：適用条件と完了条件。表現の面白さなど判断が必要な部分はメインが読む。スクリプトだけで品質を認定しない。
- `carryForward`：明示した引継ぎ時にコピーするか。「今の作品だけ」なら `false`。
- `enforcement`：「指示」は `report`。「強く指示」は `agents` または `agents+hooks`。後者の登録だけではHooksは導入されない。
- `decision`／`decisionNote`：実際の相談結果か「おまかせ」と、決めた範囲。入力値そのものは承諾の証明にならないため、Codexは実際の発言を確認する。相談の原文や作品固有の詳細は `.work/` に残し、引継ぎ対象の文面は必要な一般性を保つ。

指示を追加・変更するときにAGENTS.mdの管理区間も更新する。正本を直接編集した場合、既存の変更確認手順で意図を確認し、承諾済みなら `sync-agents` で同期する。ユーザーの直接編集を黙って取り消さない。

## 確認時点

| 識別子 | 時点 |
| --- | --- |
| `brief-complete` | 企画完了 |
| `script-complete` | 字コンテ完了 |
| `layout-complete` | コマ割り計画完了 |
| `name-complete` | ネーム完了 |
| `before-generation` | ページ生成前 |
| `after-generation` | ページ生成後 |
| `page-complete` | ページ完成 |
| `before-preview` | PNG提示前 |
| `after-preview` | PNG確認後 |
| `before-psd` | PSD作成前 |
| `after-psd` | PSD作成後 |
| `before-handoff` | 引き渡し前 |

この順序は期限を過ぎた必須事項を拾うための索引で、全工程の実施命令ではない。生成方式・依頼範囲によって通らない工程は、適用条件を照合して「対象外」とする。独自の確認時点が必要なら対応する節目を相談し、意味を変えて黙って別の時点へ置き換えない。

## 報告と根拠の照合

```powershell
python -X utf8 scripts/process_checker.py report --input .work/process-checker/report.json
```

```json
{
  "checkpoint": "page-complete",
  "scope": "page",
  "subject": "page-001",
  "revision": "v1",
  "results": [
    {
      "id": "proc-script-review",
      "status": "実施済み",
      "note": "対象の字コンテとレビュー本文を読み、指摘への対応が記録されていることを確認",
      "evidence": ["docs/story/TEXT-STORYBOARD.md", "docs/reviews/STORY-REVIEW.md"]
    }
  ]
}
```

この例のレビュー文書がなければ、実在する記録を指定する。空の雛形や「実施済み」の一文を作るだけで済ませない。入力JSONの内容を真実と認定する機能はない。

- 報告時点以前の期限の作品全体の指示と、報告対象ページの指示を照合する。報告されない項目は「未確認」とし、前回までの未解決事項を保持する。
- ページ完成時は `scope: page`、ページIDと版を必ず指定。１ページ目の合格を２ページ目へ流用しない。ページを修正したら版を更新し、旧版の記録を残して新しい版を照合する。
- 作品全体の指示も対象原稿の変更で再確認できるよう、根拠に対象原稿を含める。実施済みには実在ファイルが必要で、保存時にSHA-256を取得する。後日、根拠や指示が変わると「未確認」になる。
- 「対象外」「ユーザー回答待ち」も具体的な理由を必要とする。ユーザー回答の代作や、条件の恣意的な解釈で通過させない。回答待ちの間も無関係な作業は進められる。
- 引き渡し前は、実際のページ一覧と記録を照合する。ファイル名からページの存在を自動推測する処理はないため、メインが全対象を列挙して各ページの最新の版を報告する。
- `status` の未解決一覧が空でも、未報告の工程・ページまで確認済みとは言えない。報告内容と成果物の意味を判断するのはSkillを実行するメインである。

相談だけで漫画の工程が進んでいないターンは `{"noProgress": true, "note": "設定の説明だけで制作工程は進めていない"}` を報告できる。既存の不足事項は解消されない。作業を進めた際の照合を省くためには使用しない。

## 強い指示とHooks

まずAGENTS.mdで、その条件と実施期限を明記する。生成前の参照やユーザー回答の確認など、事後に取り戻せない条件は実行前に確認する。

Hooksを追加する場合は、環境のPython実行方法と既存Hooksを確認する。`install-hooks` の既定は設定案の表示だけで、変更しない。表示した内容への承諾、または今回の「おまかせ」の範囲を確認してから `--apply` を実行する。

```powershell
python -X utf8 scripts/process_checker.py install-hooks
python -X utf8 scripts/process_checker.py install-hooks --apply
```

提供するHooksは `UserPromptSubmit`（強い指示の参照と今回の報告を促す）と `Stop`（未報告や実施根拠不足なら１回だけ継続を求める）。報告の内容を別AIが自動審査するものではない。画像生成前の意味的な条件はAGENTS.mdとSkillで確認する。必要な場合の専用 `PreToolUse` は、対象ツール・判定可能な条件・停止時の復帰を具体的に相談して別途実装する。任意のコマンド文字列を指示ファイルから実行しない。

設定保存後は、利用するCodex環境でHooksのレビュー・信頼を行う。CLIでは `/hooks` が公式の入口。環境が非対応・Hooksが無効・Pythonが見つからない・未信頼の場合は、AGENTS.mdによる運用とHooks未稼働を区別して伝える。信頼記録の代作、無断の機能有効化、信頼を迂回する引数は使わない。新しい設定を読み込んだセッションで確認する。

同じターンでHooksが継続を求めるのは１回まで。ユーザー回答待ちは自動修正を求めない。進捗なしの相談を報告した場合も継続要求をしない。解消できない事項は理由を示して引き継ぎ、確認済みとは扱わない。エラーやロック競合は警告にし、通過を検証合格とは扱わない。

## 別の新規作品へ引き継ぐ

引継ぎ元はユーザーが明示する。キットルートで新規作成するとき：

```powershell
.\scripts\New-MangaProject.ps1 -ProjectName '新しい作品' -ProcessRequirementsFrom '../前の作品'
```

指定しなければ空のリストから始める。指定した場合はPython 3.10以上が必要。先に引継ぎ元の形式を確認し、引継ぎ対象の指示だけをコピーして強い指示を新しいAGENTS.mdへ反映する。新規作品へ移ったあとに、登録済み内容・適用条件を確認して制作を始める。

既に作成済みで、まだ指示のない作品から実行する場合：

```powershell
python -X utf8 scripts/process_checker.py import --from-project '../前の作品'
```

元作品の実施記録、素材、Hooks設定、信頼情報、有料利用や外部送信の許可は移さない。`agents+hooks` の希望は指示として保持するが、実際のHooks導入・信頼は新しい環境で別途行う。引継ぎ先に指示がある場合は停止し、ユーザーと差分を相談する。コピー後の作品同士は自動同期しない。

## 出典と検証範囲

- [公式Skillsガイド](https://learn.chatgpt.com/docs/build-skills)：Skillは手順・参照資料・任意のスクリプトをまとめ、明示呼出しまたは説明との適合で選択する仕組み。常駐監視を保証しない。
- [公式AGENTS.mdガイド](https://learn.chatgpt.com/docs/agent-configuration/agents-md)：作業開始時のプロジェクト指示の読み込み。作品ごとの強い指示を置く場所として参照。
- [公式のSkills運用例](https://developers.openai.com/blog/skills-agents-sdk)：AGENTS.mdに条件付きの必須Skill、Skillに手順、スクリプトに反復処理を置く設計の参考。
- [公式Hooksガイド](https://learn.chatgpt.com/docs/hooks)：`UserPromptSubmit`、`Stop`の入出力、`stop_hook_active`、管理対象外Hooksのレビュー・信頼、Windowsの`commandWindows`を確認。Hooksには対象外の経路があり、完全な実施保証ではない。

出典の取得・確認日は2026-09-21。登録形式・２段階の強さ・作品間の明示コピー・状態管理はキット独自の制作提案。公式仕様の確認と、この実装の動作確認・会話での効果検証は区別する。キットの自動検査・テストは配布元の `docs/publication.md` の実行確認に従う。同文書は作品へ同梱しない。
