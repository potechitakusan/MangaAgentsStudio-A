# 最初の環境設定（SETUP）

配布元のキットから作成されたこの作品フォルダで、最初に確認する設定と作画手段別の準備手順です。

---

## 1. 初回制作の確認とフォルダ構成

1. **作品フォルダでエージェントを開き直す**：配布元のキットから、作成時に表示された絶対パスの作品フォルダへCodex（または指定したAIエージェント）を開き直して新しい会話を始めます。現在の作業フォルダにこの作品の `project.json` と `AGENTS.md` があり、ローカルSkills（`.agents/skills/`）が認識されていることを確認します。開き直し方がわからない場合は、利用する環境（Windows／Mac、アプリ／VS Code）をCodexへ伝えると、[開き直しの案内](knowledge/codex-operation.md#作品フォルダでcodexを開き直す)に沿って最新公式情報を調べて説明します。
2. **フォルダの役割**：
   - `input/`：作品固有の入力データ、NovelAI / PixAI の要求JSON（`input/novelai/requests/`・`input/pixai/requests/`）、ページ構成（`input/pages/`）、組版指定（`input/typeset/`）
   - `assets/characters/`：キャラクター参照画像、`assets/references/`：背景・小物などの参照、`assets/fonts/`：作品指定フォント（任意）
   - `workflows/`：ComfyUIワークフロー（外部生成・動画試作を使う場合）
   - `output/`：生成候補画像、ページPNG／PSDビルド出力、WebUIログ
   - `docs/`：企画・字コンテ・ネーム・レビュー・進捗記録

---

## 2. 設定ファイル（3分割）とAPIキーの保存先

作品の設定ファイルは用途ごとに次の3つに分かれています（見本は `.env.example`・`.env.novelai.example`・`.env.pixai.example` で、見本ファイル自体は読み込まれません）。

| ファイル・場所 | 役割・書く内容 | 読込対象・優先順位 |
| --- | --- | --- |
| **`.env`**<br>（初回推奨） | APIキー（`NOVELAI_API_KEY`、`PIXAI_API_KEY`）や接続先URL等の**共通設定** | キー読込の第4優先（`環境変数` → `.secrets/<service>.env` → `.secrets/.env` → `.env` の順） |
| **`.secrets/novelai.env`**<br>**`.secrets/pixai.env`** | サービス別に分離したAPIキー専用ファイル（`.secrets/.env` も対応） | キー読込の第2優先（`.secrets/.env` は第3優先） |
| **OSの環境変数** | `NOVELAI_API_KEY` / `PIXAI_API_KEY` | キー読込の第1優先（最優先） |
| **`.env.novelai`** | NovelAI用のキャラクター・絵柄・背景のプロンプト変数と補助設定 | `novelai_compose.py`・`novelai_batch.py`・NovelAI WebUIが使用（APIキーは書かない。以前の版で `.env` に置いたNovelAI変数は `python -X utf8 scripts/novelai_batch.py env-migrate` で移行） |
| **`.env.pixai`** | PixAI用のキャラクター・絵柄・背景・LoRAのプロンプト変数と補助設定 | `pixai_compose.py`・`pixai_batch.py`・PixAI WebUIが使用（APIキーは書かない） |

- **キー記入時の注意**：ファイルで設定する場合は、**トークンやキーの値だけでなく、左辺の設定名と `=` も含めて**1行で書きます。左辺の設定名は公開してよい名前で、秘密にするのは右辺の値です。**会話や公開ファイル、`.env.example` 等には実値を絶対に書かないでください。**

---

## 3. 作画手段別の準備（使うものだけ設定）

### 共通：PNG組版・PSD出力に必要なPython環境と依存パッケージの準備

API通信や要求JSONの組み立て（テキストのみ）、WebUIの起動自体は **Python 3.10以上**の標準ライブラリだけで動きますが、以下の画像処理・組版・PSD工程には追加パッケージが必要です。

- **PNG組版・マスク作成・i2i/インペイント寸法確認・WebP/JPEG応答のPNG変換**：Python 3.10以上 ＋ `Pillow`
- **組版済みPSDの書き出しと再読込検証（`--write-psd`）**：**Python 3.12以上** ＋ 同梱の `scripts/requirements-composition.txt`（`Pillow==12.3.0`・`numpy==2.5.3`・`psd-tools==1.19.0`）。固定版 `numpy==2.5.3` の必要Python版は `>=3.12` です（[NumPy 2.5.3の配布情報](https://pypi.org/project/numpy/2.5.3/)、2026-10-25確認。適用範囲は同梱依存ファイルの固定版）。

> **AIエージェントへ確認・準備を任せる場合の依頼文例：**
> 「生成やAPI通信はせず、必要なPython環境と依存パッケージを確認して準備してください」

自分で作品ルートのターミナルから確認・導入する場合は、以下を実行します（Linuxでは `python` を `python3` に読み替えてください。既存のPython環境を分けたい場合は仮想環境 `venv` 等を有効化してから実行します）。

```powershell
# 1. 現在のPythonバージョンと導入済みパッケージの確認（API通信なし）
python --version
python -c "import PIL; print('Pillow OK')"
python -c "import PIL, numpy, psd_tools; print('PSD dependencies OK')"

# 2A. PSD書き出し・再読込検証まで使う場合（Python 3.12以上・同梱の固定依存版を一括導入）
python -m pip install -r scripts/requirements-composition.txt

# 2B. PNG組版・マスク作成・画像変換のみ使う場合（Python 3.10以上）
python -m pip install Pillow==12.3.0
```

### A. Codex内蔵の画像生成（imagegen）を使う場合

APIキーの追加設定は不要です。現在のCodexセッションで画像生成ツールが使えるかを確認し、[コマ割りの手順](knowledge/panel-layout-policy.md)と[ページ設定](knowledge/page-layout.md)に沿って進めます。

### B. NovelAI APIを使う場合

同梱の `scripts/novelai_api.py`・`scripts/novelai_compose.py`・`scripts/novelai_batch.py` で、キーの自動読込・契約照会・要求の組み立て・一括生成・採用・ページの組み直しができます（通信・生成自体はPython 3.10以上の標準ライブラリのみで動作し、組版・PNGの `build` には `Pillow` を使います。PSD出力は上記の共通条件に従い、Python 3.12以上と `Pillow`・`numpy`・`psd-tools` を用意します）。詳細は [NovelAI APIの接続手順](knowledge/novelai-api.md) と [NovelAIでの制作手順](knowledge/novelai-composed-production.md) を参照してください。

1. **APIキーの用意**：作品の `.env` または `.secrets/novelai.env`（あるいは環境変数 `NOVELAI_API_KEY`）に、Persistent API tokenを次の1行で書きます。
   ```dotenv
   NOVELAI_API_KEY=実際のトークン
   ```
2. **生成なしの接続確認**：作品側で「NovelAIを使いたい」「NovelAIの接続を確認して」と伝えるか、次を実行します（ファイルなし・設定行なし・空の値・形式不正・通信失敗を区別して表示します）。
   ```powershell
   python -X utf8 scripts/novelai_api.py key-status
   python -X utf8 scripts/novelai_api.py status
   ```
   `key-status` は外部通信のないローカル確認です。`status` はAPIキーを認証ヘッダーに使って契約を照会し、作品のプロンプトや画像は送りません。接続確認用の [依頼プロンプト](knowledge/novelai-api.md#確認を依頼するプロンプト) も用意しています。
3. **要求の組み立てと費用確認**：要求JSONは原則として `scripts/novelai_compose.py`（V5が既定、V4.5はユーザー指定時のみ。使い方は [標準スクリプトの説明](knowledge/novelai-api.md#compose-standard)）で組み立てます。生成コマンドは `--execute` がなければ送信しません。有効なOpus契約なら [Anlasを消費しない生成条件](knowledge/ai-production.md#novelai-opus)を確認し、1回1枚・28ステップ以下（V5は初期値23、V4.5以前は28）・標準の [ページ設定](knowledge/page-layout.md)を基準にします。採用寸法・モデル・追加機能を含めた0 Anlasの確認とV5利用上限の残量確認を行い、有料（Anlas消費）生成は明示指示がある範囲だけ実行します（契約照会の成功だけでは費用・残枠の確認完了と扱いません）。
4. **プロンプト変数編集とローカルWebUI**：キャラクター・絵柄・背景を自分で編集して再生成したい場合は [NovelAIプロンプト編集のREADME](novelai-prompts/README.md) を参照してください（依頼があった場合だけ変数化し、`.env.novelai` の直接編集とテキストからの反映を選べます）。要求JSONとページ構成の準備後は、作品ルートで `python -X utf8 .agents/skills/novelai-batch-webui/novelai_webui.py` を実行してブラウザー画面（既定ポート `8765`）からも操作できます（[NovelAI WebUIスキル](../.agents/skills/novelai-batch-webui/SKILL.md)）。

### C. PixAI APIを使う場合

同梱の `scripts/pixai_api.py`・`scripts/pixai_compose.py`・`scripts/pixai_batch.py` で、キーの読込・認証確認・要求の組み立て・一括生成・取得し直し（`fetch`）・採用・ページの組み直しができます。設定と機能（公式15モデル・LoRA・画風プリセット35種・mode・参照画像）は [PixAI APIの接続手順](knowledge/pixai-api.md) と [PixAIでの制作手順](knowledge/pixai-composed-production.md) を参照してください。

通常のテキストからの要求作成や認証確認はPython 3.10以上の標準ライブラリで動作します。**i2i・インペイントの要求作成**では元画像・マスクの寸法確認に `Pillow` が必要です。WebP/JPEG応答のPNG変換、マスク作成、ページPNGビルドにも `Pillow` を使います。PSD出力は上記の共通条件に従います。

1. **APIキーの用意**：キーは [PixAIのAPI設定](https://pixai.art/profile/edit/api) で作成し、作品の `.env` または `.secrets/pixai.env`（あるいは環境変数 `PIXAI_API_KEY`）に次の1行で書きます。
   ```dotenv
   PIXAI_API_KEY=実際のキー
   ```
2. **生成なしの接続確認**：
   ```powershell
   python -X utf8 scripts/pixai_api.py key-status
   python -X utf8 scripts/pixai_api.py status
   ```
   `key-status` は外部通信のないローカル確認です。`status` はAPIキーを認証ヘッダーに使って認証を確認し、作品のプロンプトや画像は送りません。
3. **クレジット消費の確認と生成**：PixAIの生成はクレジットを消費し、残高照会APIがないため、利用者の明示の許可がある範囲だけ `--confirm-credits` と `--cost-note` を付けて送信します（1タスク4枚候補 `batchSize: 4` は4枚分の生成になります）。途中で待機を中止してもPixAI側の作成済みタスクは続くため、再生成の前に `pixai_batch.py fetch` で取得し直します。
4. **プロンプト変数編集とローカルWebUI**：変数の編集は [PixAIプロンプト編集のREADME](pixai-prompts/README.md) を参照してください。要求JSONとページ構成の準備後は、作品ルートで `python -X utf8 .agents/skills/pixai-batch-webui/pixai_webui.py` を実行してブラウザー画面（既定ポート `8775`）からも操作できます（[PixAI WebUIスキル](../.agents/skills/pixai-batch-webui/SKILL.md)）。

### D. ローカルComfyUI・外部生成を使う場合

画像制作時にローカルのComfyUIへの相対パス・GPU・モデル・版・起動手順を確認し、秘密値を除いて `docs/experiments/` へ記録します。既存環境の起動許可はその作品でのユーザー指示に従います（モデルやLoRAを自動インストールする初期処理はありません）。コマ別作画の手順は [外部生成によるコマ作画](knowledge/external-panel-i2i.md) を参照してください。

---

## 4. 任意機能の設定（必要な場合のみ）

- **日本語推敲スキル（既定は無効）**：[OPTION.md](../OPTION.md) で日本語推敲スキルを有効にした作品では、初回作業時に `scripts/Initialize-OptionalSkills.ps1`（Linuxは `scripts/Initialize-OptionalSkills.sh`）を実行して `.agents/skills/` へ導入します。`humanizer-jp` でGitがない場合はインストールの可否を確認し、Geminiを使う `japanese-natural-writing` は利用可能な環境があっても**文章の送信と利用枠の消費許可**を必ず得てから導入します。未回答・拒否では通常の制作を続けます（[初回導入の手順](knowledge/optional-skills.md)）。
- **レビュー重点の調整（任意）**：`config/review-profiles.json` の `defaults` を作品に合わせ、必要なシーンを `scenes` へ追加できます。解決例と意味は [レビュー運用](knowledge/review-workflow.md) を参照してください。
- **動画での演出試作（任意依頼時のみ）**：動画で映画的演出を試す依頼がある場合に限り、`manga-video-previsualization` スキルと [動画試作の運用](knowledge/video-previsualization.md) を使います。動作確認済みの動画ワークフローを作品の `workflows/` へ用意し、モデルと入力の対応を確認してから実行します（人物参照は `assets/characters/`、動画・音声は `output/`、条件・所要時間・採否は `docs/experiments/` へ保存）。通常の漫画制作の前提作業にはしません。

---

## 5. PNG確認からPSD引き渡しまでの流れ

[ノウハウ一覧](MANGA-KNOWHOW.md)から必要な知識を選んで制作を進めます。

1. **PNGプレビューで確認・修正**：まずPNGプレビューを作成して確認・修正します。後でPSDにできるよう、分離して制作した素材とセリフ原文を保持します。
2. **希望時のみPSD作成・検証**：PNGの修正がなくなってからPSD作成へ進みます。PSD作成の指示がなければ作るか聞いて回答を待ち、既に指示があれば再確認しません。PSD作成に進む際は作成・再読込の手段と、CLIP STUDIO PAINTで確認できる環境を調べ、PNGの確認結果・PSD作成指示・仕様を [引き継ぎ記録](production/PSD-HANDOFF.md) と [セリフ原文](production/DIALOGUE.md) へ残します（詳細は [PSD引き渡しルール](knowledge/psd-handoff.md)）。
3. **仕上げ・公開**：依頼されたPSDは作成・検証して人間に引き渡し、原則として人間がCLIP STUDIO PAINTで仕上げ・公開します。CBZは明示指定時だけ作成します。
