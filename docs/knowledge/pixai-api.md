# PixAI APIの接続手順

対象は作品に同梱する `scripts/pixai_api.py`（１タスクの生成）・`scripts/pixai_compose.py`（要求の組み立て）・`scripts/pixai_batch.py`（コマ別の一括生成・採用・ページの組み直し）。Python 3.10以上の標準ライブラリだけで動く（WebP・JPEGの応答をPNGへ変換するときと build だけ Pillow を使う）。ブラウザーの起動・操作は行わない。作品の `project.json` が必要で、キットの雛形では実行しない。

作品側で「PixAIを使いたい」「PixAIの接続を確認して」と依頼されたら、Codexはこの手順で案内する。キーの設定が必要なときに次の記入例を示し、設定済みなら再入力を求めない。制作の手順（プロンプトの組み立て・LoRA・参照画像・採用・組版）は [PixAIでの制作手順](pixai-composed-production.md)。

## キーを用意する

PixAIのAPIキーを使う。キーは [PixAIのプロフィールのAPI設定](https://pixai.art/profile/edit/api) で作る（会員プランならすぐ発行、メール申請は審査あり。公式FAQ）。メールアドレス・ログインパスワード・ブラウザーのトークンは渡さない。キーを会話・プロンプト・生成要求JSONへ貼らず、次のいずれかへ利用者自身が設定する。

- Codexや端末のプロセスから見える環境変数 `PIXAI_API_KEY`
- 作品内の共通設定 `.env`、または `.secrets/pixai.env`。内容は `PIXAI_API_KEY=` の右側へ実値を記入する

```dotenv
PIXAI_API_KEY=実際のキー
```

**キー名は `PIXAI_API_KEY` で、秘密にするのは `=` の右辺のキー。** 環境変数 → `.secrets/pixai.env` → `.secrets/.env` → `.env` の順に、最初の空でない値を使う。書式（UTF-8、引用符・`export`・行末コメント）と、エラーで秘密値・入力行を表示しない扱いは NovelAI のキー読込と同じ実装方針。`.env.example` は項目名の見本で読み込まない。`.secrets/`・`.env`・`.env.*`（見本を除く）はGit除外済み。

### 設定ファイルの分け方

作品の設定ファイルは３つに分ける。

| ファイル | 置くもの | 見本 |
| --- | --- | --- |
| `.env` | APIキー・接続先URLなどの共通設定（`NOVELAI_API_KEY`・`PIXAI_API_KEY`・`COMFYUI_URL` 等） | `.env.example` |
| `.env.novelai` | NovelAI用のキャラクター・絵柄・背景のプロンプト変数と補助設定 | `.env.novelai.example` |
| `.env.pixai` | PixAI用のキャラクター・絵柄・背景・LoRAのプロンプト変数と補助設定 | `.env.pixai.example` |

APIキーは `.env` のほか、`.secrets/` や環境変数にも置ける。`pixai_batch.py` は `.env.pixai` と環境変数のプロンプト変数・補助設定だけを読み、APIキーや他のファイルの行を読まない。

## 生成せず確認する

```powershell
python -X utf8 scripts/pixai_api.py key-status
python -X utf8 scripts/pixai_api.py status
```

`key-status` は通信しない。`status` は存在しないタスクID（`GET /v1/task/0`）を１回照会し、404なら「認証は通った」、401なら「キーが無効」と判定する（2026-10-25に実キーで確認：有効なキーは `404 not found`、無効なキーは `401 Invalid token`）。画像生成・クレジット消費はしない。

**クレジットの残高・消費を照会するAPIは公式文書にない。** 契約・残高はPixAIの画面で確認する。スクリプトは無料を判定できないため、送信には利用者の明示の許可が必要（下記）。

## 公式仕様（確認した事実）

出典：[PixAI API Documentation](https://platform.pixai.art/en/docs)（[llms-full.txt](https://platform.pixai.art/llms-full.txt) と各ページのTypeScript定義）。取得日：2026-10-25。

| 項目 | 内容 |
| --- | --- |
| 接続先・認証 | `https://api.pixai.art`、全要求に `Authorization: Bearer <key>` |
| v2 生成 | `POST /v2/image/create`。必須は `modelVersionId`・`prompt`。任意：`negativePrompt`、`aspectRatio`（`1:1`・`2:3`・`3:2`・`3:4`・`4:3`・`3:5`・`5:3`・`9:16`・`16:9`・`1:3`・`3:1`、既定 `1:1`）、`size`（`1k`・`1.5k`、既定 `1k`）、`mode`（`lite`・`standard`・`pro`・`ultra`。Tsubaki.2・Tsubaki.3 だけ。他のモデルでは `400 INVALID_ARGUMENT`）、`style`（`{"type": "preset", "key": …}` 35種 か `{"type": "custom", "custom": …}`。Tsubaki.2・Tsubaki.3 系だけ、他では無視）、`loras`（最大5件。`modelId`＝LoRAのバージョンID、`weight` 0〜1・既定1、`triggerWords` 省略時はモデルの既定）、`seed`、`batchSize`（1か4、既定1）、`sampling`（`method`・`steps` 1〜100・`cfgScale`。SDXL・SD v1 だけ）、`promptHelper`（`enable`・`disable`、**既定は enable**＝送信前にプロンプトを書き換える）、`callbackUrl`。`modelId` は非推奨 |
| v1 生成 | `POST /v1/task`。`{"parameters": {…}, "callbackUrl"}`。`parameters` の公式項目：`prompts`（4096字以内。丸括弧の強調に対応、角括弧・波括弧は非対応）、`modelId`、`width`・`height`（512〜1280）、`lora`（`{バージョンID: 重み}`、maxProperties 3。説明文には「最大10」ともある）、`batchSize`（1〜4）、`inferenceProfile`、`modelStyle`（`key`・`custom`・`styleKeyRef`）、`enableTile`（元画像があり upscale > 1 のとき）、`upscale`（Hires Fix。長辺2048px以内に抑える）、`upscaleSampler`、`enableADetailer`（顔の修正）、`promptHelper`（`{"enable": bool}`）。このページはドキュメントの目次から外れている（URLは有効） |
| タスク | `GET /v1/task/{taskId}`。`status` は `waiting`・`running`・`completed`・`failed`・`cancelled`。完了時 `outputs.mediaIds`・`outputs.mediaUrls`（取得できない画像は `null`）。`mediaSafetyLevel`・`textSafetyLevel`（`nsfw`・`safe`。ない場合も安全を意味しない） |
| メディア | `GET /v1/media/{mediaId}`（`urls` の `PUBLIC`・`THUMBNAIL` 等）、`GET /v1/media/{mediaId}/image`（302で画像へ）、`POST /v1/media/upload`（画像・動画の本体をそのまま送る。`Content-Type` と正確な `Content-Length` が必要。multipartは不可。応答の `id` が mediaId） |
| 制限 | `waiting` のタスクは同時に10件まで（`running` は数えない）。要求の頻度の制限はないが、ポーリングは1.5秒に1回以下、再試行は指数バックオフ。動画生成、PixAI Reference Pro・PixAI Edit・PixAI Edit Lite は未対応（開発中） |
| 保存 | 生成画像は無期限には保存されない。完了後すぐ取得する。API生成は非公開で、公開の生成履歴に出ない |
| 解像度（v2） | 下表。すべて16の倍数。`1.5k` は長辺1536px |
| モデル | 推奨：Tsubaki.2（DiT、`1983308862240288769`。プロンプト理解・人体・複数人物の描写が強い）、Haruka v2（SDXL、`1861558740588989558`。安定・手が正確）、Hoshino v2（SDXL、`1954632828118619567`。日本で人気の作風）。サンプラーは3モデルとも Euler a・Euler・LMS・Heun・DPM2 Karras・DPM2 a Karras・DDIM・DPM++ 2M Karras・DPM++ 2S a Karras・DPM++ SDE Karras・DPM++ 2M SDE Karras・Restart。他のモデル・LoRAは `https://pixai.art/model/<モデルID>/<バージョンID>` の最後の数字を使う。Tsubaki.3 は一覧にないが、v2 生成の説明は `mode`・`style` の対象に挙げる。キットは公式モデル15種を収録している（下の「モデルの一覧と追加」） |
| 権利 | APIで生成した画像の著作権は利用者に帰属（第三者の権利・法令の確認は利用者の責任）。公式モデルの商用利用は承認された利用者に許可、モデルファイルの再配布は禁止。[利用規約](https://pixai.art/terms) |

| 縦横比 | 1k | 1.5k |
| --- | --- | --- |
| 1:1 | 1024×1024 | 1536×1536 |
| 2:3 | 848×1280 | 1024×1536 |
| 3:2 | 1280×848 | 1536×1024 |
| 3:4 | 864×1152 | 1152×1536 |
| 4:3 | 1152×864 | 1536×1152 |
| 3:5 | 768×1280 | 912×1536 |
| 5:3 | 1280×768 | 1536×912 |
| 9:16 | 720×1280 | 864×1536 |
| 16:9 | 1280×720 | 1536×864 |
| 1:3 | 512×1536 | 512×1536 |
| 3:1 | 1536×512 | 1536×512 |

### 公式文書にない項目

[公式JavaScriptクライアント](https://github.com/pixai-art/pixai-client-js)（`src/parameters.types.ts`、2026-10-25取得）の v1 の型には、現行の公式文書にない次の項目がある。予告なく使えなくなる可能性があるため、`pixai_api.py` はこれらを送る要求に `--allow-unverified` を求め、実行記録の `unverifiedParameters` に残す。受理と効果は下の「[公式文書にない項目の確認結果](#unverified-results)」。

- `negativePrompts`、`seed`、`samplingSteps`、`samplingMethod`、`cfgScale`、`clipSkip`、`vaeModelId`
- i2i：`mediaId` または `mediaUrl`（元画像）、`strength`（変化量）、`maskMediaId`・`maskMediaUrl`（インペイント）
- `controlNets`：`[{"type": "openpose" 等, "mediaId", "weight"}]`。種類は `dwpose`・`openpose_full`・`canny`・`depth`・`hed`・`mlsd`・`openpose`・`seg`・`normal`・`scribble`
- `ipAdapter`：`{"enabled": true, "referenceImages": [mediaId…]}`。型の説明は「参照画像の画風・構図・顔を写す」
- `latentCouple`（領域別のプロンプト）、`upscaler`・`upscaleDenoisingSteps`・`upscaleDenoisingStrength`、`enlarge`・`enlargeModel`

<a id="models"></a>

### モデルの一覧と追加（バージョンIDを調べずに使う）

作品の `config/pixai-models.json` に、PixAIの公式モデル15種のバージョンID・種類・送れる項目・利用条件を収録している。`pixai_compose.py --model <名前>` で選ぶだけでよく、利用者がバージョンIDを調べる必要はない。一覧は `python -X utf8 scripts/pixai_models.py list`。

出典：[PixAI公式アカウントのモデル一覧ページ](https://pixai.art/en/@pixai-official/artworks/models)に埋め込まれたデータ（2026-10-25取得）。公式文書の推奨3モデルのバージョンIDと一致することを確かめた。PixAI Edit・PixAI Reference Pro はAPI未対応のため収録しない。公式モデルはすべて商用可（ページの `permittedUse`）。利用回数はページの表示（2026-10-25）で、Haruka v2 が約2.5億回、Tsubaki.2 が約1.1億回、Haruka・Tsubaki が各3千万回台。

| 名前（`--model`） | モデル | 種類 | mode・画風プリセット | 主な特徴（ページの表示・公式の説明） |
| --- | --- | --- | --- | --- |
| `tsubaki3` | Tsubaki.3 | DiT（`MMDIT26B_MODEL`） | 可。既定 mode `pro`（`standard` は拒否） | 最新。色の制御・プロンプトへの追従 |
| `tsubaki3-flash` | Tsubaki.3 Flash | DiT（同上） | 可（mode は既定で送らない） | 高速版（8ステップ）。除外（negativePrompt）は非対応と表示 |
| `tsubaki2` | Tsubaki.2 | DiT（`MMDIT26A_MODEL`） | 可。既定 mode `standard` | キットの既定。複数人物・照明・動きのあるポーズ |
| `tsubaki`・`tsubaki-v1-1`・`tsubaki-flash` | Tsubaki・Tsubaki v1.1・Tsubaki Flash | DiT（`DIT7B_MODEL`） | 不可（公式に Tsubaki.2・Tsubaki.3 系だけ） | 初代の系統。自然文・複数人物 |
| `serin` | Serin | DiT（`DIT7B_MODEL`） | 不可 | 韓国のウェブトゥーン・ファッション風 |
| `haruka2`・`haruka` | Haruka v2・Haruka | SDXL | 不可 | 安定した塗り・正確な手 |
| `hoshino2` | Hoshino v2 | SDXL | 不可 | 日本で人気の作風・レトロなアニメ調 |
| `otome2` | Otome v2 | SDXL | 不可 | 男性キャラクター向け |
| `hinata2`・`nagi`・`crystalize`・`eternal` | Hinata v2・Nagi・Crystalize・Eternal | SDXL | 不可 | 画風の再現向け |

APIでの受理と mode は下の「[モデルの確認結果](#model-results)」、各モデルと画風プリセットの絵柄はキット専用の閲覧見本 `resources/pixai-model-samples/index.html`（基本的に同じプロンプトで各１枚）。

**一覧にないモデル**（ユーザーが作ったモデル等）は、モデルページのURLから作品の一覧へ登録する。

```powershell
python -X utf8 scripts/pixai_models.py info --url https://pixai.art/model/<モデルID>/<バージョンID>   # 表示だけ
python -X utf8 scripts/pixai_models.py add my-model --url https://pixai.art/model/<モデルID>/<バージョンID>
```

- 公開のモデルページを１回取得し、ページに埋め込まれたデータからバージョンID・種類・除外の対応・利用条件（商用・オンライン共有・作者表記）を読む。キーを送らず、ログインせず、クレジットを使わない。版を指定しないURLではページの最新の版を使う。
- 種類から mode・画風プリセットの可否を決める（`MMDIT26*`＝Tsubaki.2・Tsubaki.3 系だけ可）。登録したモデルの `api` は「未検証」で、mode は既定で送らない。
- LoRAのページを渡すと、バージョンIDを表示して登録を断る（LoRAは `.env.pixai` の `PIXAI_LORA_…` に書く）。
- 商用不可のモデルは登録時に注意を表示する。ユーザーが作ったモデルの多くは個人利用のみ（2026-10-25のランキング上位で確認）で、インターネット公開・販売の可否は利用者がモデルページで確かめる。
- 埋め込みデータはPixAIの公式APIではなく、形式が変わると読めなくなる。読めない場合は、利用者にモデルページで版のタブ（「v1」等）を押したURLを写してもらい、`--model-version-id` と `--model-type dit|sdxl` で指定する。WebFetch等の要約ではバージョンIDが落ちることがある。
- 消費クレジットはAPIで照会できない。利用者がPixAIのプロフィールの「Membership & Credits」の使用履歴で確認する（[User Profile](https://support.pixai.art/en/articles/11822651-user-profile)、2026-10-25確認）。

`pixai_api.py` は、一覧の `modes_rejected`（拒否される mode）・`controlnet: false`・`inpaint: false` に当たる要求を送信前に止め、`modes_accepted` にない mode は「未確認」と表示する。

v1 の公式文書が `modelStyle`・`inferenceProfile` の説明で触れる `GET /generationModel/{modelVersionId}/style-keys`・`GET /model/{modelId}/version/{versionId}/inference-profiles` は、実キーでの照会がGraphQLの要求を求める400になり使えない（2026-10-25）。スクリプトは使わない。

## 要求JSONの形

`input/pixai/requests/<ID>.json`（単発は任意の作品内のJSON）。標準は v2。

```json
{
  "api": "v2",
  "body": {
    "modelVersionId": "1983308862240288769",
    "prompt": "1girl, solo, ${PIXAI_CHAR_MIO}, standing, upper body, school rooftop, masterpiece, best quality",
    "negativePrompt": "text, speech bubble, panel border, watermark",
    "aspectRatio": "2:3", "size": "1k", "mode": "standard",
    "style": {"type": "preset", "key": "moe-pastel"},
    "loras": [{"modelId": "${PIXAI_LORA_MIO}", "weight": 0.8}],
    "seed": 12345, "batchSize": 1, "promptHelper": "disable"
  }
}
```

v1 は `{"api": "v1", "parameters": {…}}`。作品内の画像は、このキット独自の項目 `mediaFile`（i2i）・`maskMediaFile`・`controlNets[].mediaFile`・`ipAdapter.referenceFiles`（配列）に相対パスで書く。送信時に `POST /v1/media/upload` でアップロードし、`mediaId`・`maskMediaId`・`referenceImages` へ置き換えて送る。同じ内容（SHA-256）の画像は `output/pixai/uploads.json` の mediaId を使い回す（古いIDが使えなくなった場合はこのファイルの該当行を消す）。`model_type`（`dit`・`sdxl`）は既知でないモデルの点検用の注記で、送信しない。

`pixai_api.py` の検証と既定（キットの実装方針）：

- 公式文書にない v2 の項目と、`callbackUrl`（完了はスクリプトが照会する）は拒否する。
- `aspectRatio` がなければ `config/page-layout.json` の `generationCanvas` に最も近い比を補う。`size` の既定は `1k`、`batchSize` は1、`seed` は未指定なら乱数（送った値は記録に残る）。
- **`promptHelper` の既定は `disable`**（公式の既定は enable）。字コンテとプロンプトの照合を保つため。使う場合は要求に `enable` と書く（送信前の点検で警告する）。
- `config/pixai-models.json` の一覧のモデルでは、mode に非対応のモデル（SDXL・初代Tsubaki系）の `mode`、拒否される `mode`（Tsubaki.3 の `standard`・`lite`、Tsubaki.3 Flash の `pro`）、ControlNet・インペイントに非対応のモデル（Tsubaki.2 等）への ControlNet・マスクを止める。style に非対応のモデルの `style`・DiTの `sampling`・除外に非対応のモデルの `negativePrompt`・受理が未確認の `mode`・一覧にないDiTのモデルの `mode` は注意を表示する。
- LoRAは作品の `config/pixai-loras.json`（`pixai_models.py lora` が記録）で元モデルの種類を照合し、生成モデルと違えば注意を表示する（通信しない）。
- 費用は自動見積りしない。

## 確認後に生成する

```powershell
python -X utf8 scripts/pixai_api.py generate --request input/pixai-request.json
python -X utf8 scripts/pixai_api.py generate --request input/pixai-request.json --output output/pixai/test-001.png --execute --confirm-credits --cost-note 'クレジット残高と許可範囲（例：Tsubaki.2 standard 1k を1枚、2026-10-25に利用者が許可）'
```

送信なしの段階はキーを読まず通信もしない。**ユーザーが今回の範囲でPixAIのクレジットを消費することを明示指示した場合だけ** `--confirm-credits` を付け、`--cost-note` に確認した残高・会員プラン・許可範囲を記す。キーの設定、接続確認や生成の依頼だけでは有料利用の許可とみなさない。公式文書にない項目を使う要求は、利用者が使うことを了承した場合だけ `--allow-unverified` も付ける。

送信の流れと記録（実装方針）：

1. 同名の画像・記録があれば止める。`rNNN.request.json`（要求の整形版）と実行記録 `rNNN.pixai.json` を送信前に作る。キーは記録しない。
2. v1 の作品内画像をアップロードする。失敗したらタスクを作らずに止め、記録を `failed/` へ移す。
3. タスクを作る（`rNNN.request-body.json` は送信バイトそのもの）。**作成は自動再送しない。** HTTP 4xx はタスクが作られていないため記録を `failed/` へ移す。通信障害・5xx・応答不正は結果不明として記録を残す（PixAI側を確認してから扱う）。
4. `GET /v1/task/{id}` を3秒から始めて1.3倍ずつ、最大10秒の間隔で照会する（公式の1.5秒以上）。照会の通信障害は３回まで照会し直す（読み取りなので生成の再送ではない）。既定の待ち時間は900秒（`--timeout`）。Tsubaki.3 の pro は１枚でも1分以上かかる。
5. 完了したら `mediaUrls`（ないときは `GET /v1/media/{id}` の `PUBLIC`）から**認証ヘッダーを付けずに**画像を取得する（キーを他のホストへ送らない）。PNGはそのまま、WebP・JPEGは Pillow でPNGへ変換し、構造・CRC・実寸を確かめて保存する。`batchSize` 4 は `r001`〜`r004` のように連番で保存する。
6. タスクが `failed`・`cancelled` で終わった場合は記録を `failed/` へ移す（クレジットの消費はPixAI側で確認）。待ち時間の上限・中止・画像の取得失敗では、taskId 付きの記録が残る。`python -X utf8 scripts/pixai_api.py fetch --record <rNNN.pixai.json>`（一括は `pixai_batch.py fetch`）で、**生成を再送せずに**取得し直せる。

４枚のうち一部だけ保存できた場合も停止し、WebUIと一括の `fetch` から残りを取得し直せる。保存済み画像は保持する。一部保存済みの記録を `failed/` へ移して再生成する扱いにはせず、先に `fetch` で残りを確認する。

クレジットの実消費は自動測定しないため、実行記録の `actualCreditCost` は `null` とする。生成画像と要求JSONは作品の制作資料であり、公開時はメタ情報を除去する。

## 設定・接続に問題があるとき

| 表示 | 意味と案内 |
| --- | --- |
| 設定不備：ファイルなし・設定行なし・値が空・形式不正 | 表示された読込元と記入例に沿って `PIXAI_API_KEY=` の行を直す |
| 認証失敗：HTTP 401 | 読み込んだキーが無効。キーの作り直し・読込元（`key-status`）を確認する |
| クレジット不足：HTTP 402 | クレジットが足りない。PixAIの画面で確認する |
| 入力エラー：HTTP 400・422 | 要求の値が受け付けられなかった。応答の code・message を表示する（例：SDXLのモデルに mode を送った）。タスクは作られていない。`unknown inferenceProfile` はそのモデルで使えない mode を送ったことを示し、別の mode（pro・ultra 等）が必要な可能性を案内する |
| 利用制限：HTTP 429 | `waiting` のタスクが10件に達したか、利用制限。待ってから送る |
| 通信障害・サーバーエラー | 作成の要求なら結果不明として扱い、再送前にPixAI側を確認する |

## 確認を依頼するプロンプト

```text
このプロジェクトのPixAI接続を確認してください。
AGENTS.md、docs/SETUP.md、docs/knowledge/pixai-api.mdを読んでください。
キーは .env（または環境変数・.secrets/pixai.env）の PIXAI_API_KEY に用意しました。
秘密ファイルの本文やキーの実値は表示しないでください。
scripts/pixai_api.pyのkey-status、続いてstatusを実行し、キーの読込元と認証の成否を教えてください。
今回は画像生成とクレジット消費を許可しません。ブラウザーは操作しないでください。
```

<a id="results"></a>

## 実生成での確認結果

確認日：2026-10-25。キットの配布テストと作品での利用で確かめた。各条件1〜数枚の観察で、再現性・モデル更新後の挙動は保証しない。

### 基本の生成と記録

| 項目 | 結果 |
| --- | --- |
| v2 の生成 | 受理。応答画像は WebP（`mediaUrls` の公開URL）で、スクリプトがPNGへ変換して保存する。縦横比 1:1・2:3・3:4・3:5・4:3・16:9、`size` 1.5k、`batchSize` 4 を受理 |
| `POST /v1/media/upload`（PNG） | 受理。応答の `id` を mediaId として使える |
| v1 の `seed` | 同じ seed の2枚は構図・人物・ポーズがほぼ同じで、細部だけ違う（画素の平均差 6.7）。v2 も同じ傾向（Tsubaki.2、平均差 19）。画素単位では一致しない |
| 人物の一貫性 | 外見を毎回同じ語で書いた v2（`.env.pixai` の変数）で、14コマを通して髪・帽子の飾り・外套の柄・連れの動物が保たれた。参照画像（IP-Adapter）だけでは服の細部（帽子の宝石・ブラウスの襟）が保たれにくい |
| 連続生成 | 1枚1分以上かかるモデルでは、複数タスクの合計が実行環境のコマンド待機時間を超えることがある。一括生成はその環境の継続実行の仕組みを使う |

<a id="model-results"></a>

### モデルの確認結果

| 項目 | 結果 |
| --- | --- |
| 受理 | `config/pixai-models.json` の15種すべて、v2・2:3・1k で受理・完了（mode に非対応のモデルは mode なし、Tsubaki.3 Flash は mode・除外なし） |
| mode（Tsubaki.3） | `pro`・`ultra` を受理（ultra は pro とほぼ同じ絵）。`standard`・`lite` は `422 INVALID_INPUT unknown inferenceProfile`（タスク未作成） |
| mode（Tsubaki.3 Flash） | mode なしで受理。`pro` は 422。他の mode は未確認 |
| mode（Tsubaki.2） | `lite`（standard とほぼ同じ絵）・`standard`・`pro`・`ultra`（どちらも髪が金色・暖色の柔らかい塗りに変わった）をすべて受理 |
| 生成時間（作成〜完了、1k・1枚） | Tsubaki.3 pro・ultra は1分以上。Tsubaki.2 は lite 約10秒・standard 約20秒・pro と ultra 約50秒。他のモデルは15〜72秒（Haruka v2 約50秒、Tsubaki 約70秒） |
| 絵柄 | モデルごとに大きく異なる。Tsubaki.3・Tsubaki.3 Flash はほぼ同じ構図。Tsubaki v1.1・Serin・Eternal は背景の公園がほとんど出ず、Tsubaki・Tsubaki Flash も街路寄りだった |
| 画風プリセット | Tsubaki.2（standard）で35種すべて受理。`flat-anime-pastel` はプロンプトにない頭の上の輪（既存作品を連想させる意匠）を描きやすく、除外に `halo` を入れても出た |
| 見本 | キット専用の `resources/pixai-model-samples/index.html`（モデル15種・画風プリセット35種。新規作品へはコピーしない） |

<a id="unverified-results"></a>

### 公式文書にない項目の確認結果

元画像はモデル見本の Tsubaki.3・Haruka v2 等。送信には `--allow-unverified` が必要。

| 項目 | 結果 | 状態 |
| --- | --- | --- |
| <a id="inpaint-results"></a>**インペイント**（v1 の `mediaId`＋`maskMediaId`＋`strength`。Tsubaki.3） | **白＝描き直す**。小さいマスク（画面の3%）でカップをリンゴに替える課題は 8/8 成功（1枚・4枚・strength 0.9・`inferenceProfile` pro＋`modelStyle` の各条件）。カップを消して手を組ませる課題も成功。頭に赤いベレー帽を足す課題は、小さいマスク（6%）2/4・大きいマスク（17%）2/4 で、外れた4枚は「ベレー帽をかぶった小さな猫」が描かれた（プロンプトの `cat ears` の影響と推定）。マスクの外は元画像のまま（画素の平均差 0.006〜0.05） | 受理・効果あり |
| インペイントのマスクの大きさ | 大きいマスク（16〜17%）・特大マスク（36%）でも描き足しは成功したが、**マスク内の別の部分も描き変わった**（胸のリボンの形、首の鈴が消える、特大では口元・表情）。Haruka v2 で目にかかる大きいマスクでは目の色・表情が変わった。マスクは描き足す物と、それが入る空きだけに絞り、顔・残したい小物は外す | 観察 |
| インペイント（Haruka v2・SDXL） | ベレー帽を足す課題は小さいマスク・大きいマスクとも成功。ただしマスクの外も全体にわずかに変わった（平均差 1.7〜2.0。Tsubaki.3 の約100倍） | 受理・効果あり |
| インペイント（Tsubaki.2） | `400 40000000 This feature is not yet supported for this model`（タスク未作成）。`pixai_api.py` は一覧の `inpaint: false` のモデルへの送信を止める。Tsubaki.2 の画像を直すときは Tsubaki.3 でインペイントする（背景の輪を消す課題で4枚中3枚成功、マスクの外は元のまま） | 非対応 |
| インペイントの時間 | 1件1〜2分（費用は下の「[費用](#costs)」） | 確認事実 |
| i2i（`mediaId`＋`strength`、プロンプトで公園を雪の公園に変える） | Haruka v2：0.3 はほぼ元のまま、0.6 は構図を保って地面と木に雪、0.9 は構図・ポーズを保って雪景色（服は長袖に変化）。Tsubaki.3 の 0.6 は雪が舞う程度の小さな変化 | 受理・効果あり |
| **latentCouple**（`{"type": "rect", "divisions": ["1:1","1:2","1:2"], "positions": ["0:0","0:0","0:1"], "weights": [0.2,0.8,0.8]}`、プロンプトを ` AND ` で区切る：全体 AND 左 AND 右） | Haruka v2：使わない場合は髪と服が入れ違った（赤髪＋黄色の雨がっぱ）が、使うと「赤髪＋緑の服」が左、「青髪＋黄色の雨がっぱ」が右に描き分けられ、`positions` を入れ替えると左右も入れ替わった。**ただし3人目が増えた。** 全体の重みを 0.05 にする・全体の領域をなくす書き方では、人数・服の混ざりがむしろ増えた。Tsubaki.2 では受理されたが効かなかった | SDXLで受理・効果あり。人数が増える問題が未解決 |
| ControlNet（元画像は普通の絵。Haruka v2） | `canny`：階段・髪形・かばん・ポーズまで元画像の構図を強く写した。`depth`：階段の手すり・後ろ向きの構図を写した（線はやや荒れる）。`openpose`：重み1.0では胴体のアップに崩れ、0.5では後ろ向きの構図に寄った程度（普通の絵ではポーズの指定として効かない。骨格画像は未試行）。`scribble`：タスクは作られたが約2秒で `failed`（画像なし） | canny・depth は効果あり |
| ControlNet（Tsubaki.2） | `403 40300044 This model cannot be used with ControlNets.`（タスク未作成）。モデルページの対応表でも Tsubaki.2・初代Tsubaki系・Hinata v2 は `controlnet: false`。`pixai_api.py` は一覧の `controlnet: false` のモデルへの送信を止める | 非対応 |
| Hires（`upscale` 1.5） | 1272×1920 で出力され、顔などの描き込みが細かくなった。約30秒 | 受理・効果あり |
| ADetailer（`enableADetailer`） | 顔の描き込みがわずかに変わる程度（同じ seed との比較） | 受理・効果は小さい |
| `clipSkip` 2（v1・Haruka v2） | 同じ seed の画像と見分けがつかない（平均差は seed の揺れと同じ 6.7） | 受理・効果は確認できず |
| v2 の `sampling`（Haruka v2） | `steps` 12 は小さな変化。`cfgScale` 10 は色が濃くなり、ポーズ・目の色も変わった | 受理・効果あり |
| v1 の `ipAdapter`（参照画像） | Tsubaki.2・Haruka v2 で受理。**Haruka v2** は参照画像の意匠（頭身・杖の形・耳飾り・小物）を強く写すが、参照画像の背景色による色かぶりと、プロンプトの動作・表情・背景の無視が出やすい。**Tsubaki.2**（`modelStyle` のプリセット併用）は色が自然でプロンプトの動作に従い、意匠の反映は帽子の色・杖の形など一部。２人分の参照画像を１要求に入れると、両方の要素が混ざる | 受理・効果あり |
| v1 の `inferenceProfile`＋`modelStyle`（Tsubaki.3） | `pro`＋プリセット `paper-watercolor` で、はっきり水彩調の別の絵になった。v1 でも画風プリセットが効く | 受理・効果あり |
| v1 の `negativePrompts` | 受理 | 受理 |

<a id="costs"></a>

### 費用（クレジット）

APIでは照会できないため、実行記録の `actualCreditCost` は `null`。利用者がPixAIのプロフィールの「Membership & Credits」の使用履歴で確認する。

| モデル・条件 | 1タスクの消費 | 根拠 |
| --- | --- | --- |
| Tsubaki.3・pro・1k（新規生成・インペイント） | 1枚4,000、4枚7,000 | 利用者が利用履歴で確認 |
| Tsubaki.2・standard・1k（画風プリセット付き） | 1枚 約2,700 | 利用履歴の一部からの推定 |
| Haruka v2・v1・1280×848 | 1枚 約1,200〜1,500 | 利用履歴の一部からの推定 |
| 上記以外 | 未確認 | ― |

## 出典・確認範囲

確認日：2026-10-25。確認事実は上の公式ページ（Docs・FAQ・Limits・Models・Supported Resolutions・Webhook・Copyright・createImage・createGenerationTask・getTask・getMedia・uploadMedia）の記載と、実キーでの `GET /v1/task/0`・`GET /v1/media/1`（404）と無効キー（401）、style-keys・inference-profiles（400）の応答、上の「実生成での確認結果」。**LoRA の効果と、上の表以外のクレジットの消費量は未確認。** 既定値・保存規則・費用確認フラグ・ポーリング間隔はキットの実装方針。PixAIのAPIはベータ版で、公式文書の版の間にも食い違い（v1 の LoRA の件数等）があるため、送信直前に公式文書を再確認する。
