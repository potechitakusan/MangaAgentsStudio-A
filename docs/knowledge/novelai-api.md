# NovelAI APIの接続手順

対象は作品に同梱する `scripts/novelai_api.py`。Python 3.10以上の標準ライブラリだけで動く。ブラウザーの起動・操作は行わない。作品の `project.json` が必要で、キットの雛形では実行しない。

作品側で「NovelAIを使いたい」「NovelAIの接続を確認して」と依頼されたら、Codexはこの手順で案内する。利用者に細かな確認用プロンプトを書くことを要求しない。キーの設定が必要なときに次の記入例を示し、設定済みなら再入力を求めない。

## キーを用意する

NovelAIのPersistent API tokenを使用する。メールアドレス・ログインパスワードは渡さない。キーを会話・プロンプト・生成要求JSONへ貼らず、次のいずれかへ利用者自身が設定する。

- Codexや端末のプロセスから見える環境変数 `NOVELAI_API_KEY`
- 作品内の `.secrets/novelai.env`。内容は `NOVELAI_API_KEY=` の右側へ実値を記入する

ファイル内にも左辺の設定名が必要。次の１行を記入し、「実際のトークン」の部分を自分のPersistent API tokenに置き換える。トークンだけを１行に書かない。

```dotenv
NOVELAI_API_KEY=実際のトークン
```

**キー名は `NOVELAI_API_KEY` で、秘密にするのは `=` の右辺のトークン。** 左辺の設定名を説明や会話に書いても秘密値の共有にはならない。トークンの実値を会話へ貼る必要はない。

環境変数 → `.secrets/novelai.env` → `.secrets/.env` → `.env` の順に、最初の空でない値を使う。ファイルはUTF-8（BOMありも可）、１行の `NOVELAI_API_KEY=値` 形式。引用符、行頭の `export`、値の後の空白＋`#`コメントに対応する。変数展開・コマンド実行はしない。同じファイルのキー重複や、作品外を指すリンクはエラーにする。

`.env.example` は項目名の見本で、読み込まない。`.secrets/` と `.env` はGit除外済み。環境変数が優先されるため、以前のキーが設定されているとファイルのキーへ切り替わらない。下記の `key-status` で読込元を確認する。キーの実値・一部・長さは表示しない。

## 生成せず確認する

作品ルートで実行する。スクリプトは自身の配置から作品ルートを解決するため、別の作業フォルダから呼んでも他作品の `.env` は探さない。

```powershell
python -X utf8 scripts/novelai_api.py key-status
python -X utf8 scripts/novelai_api.py status
```

`key-status` は通信しない。`status` は公式画像APIの `GET /user/subscription` を１回呼び、契約の有効状態、tier、期限、応答に含まれる残量の数値だけを表示する。API応答の全文・決済情報・メールアドレスは出力しない。画像生成を要求せず、接続結果を自動でファイルへ保存しない。

この実装は `active=true` かつ `tier=3` をOpus照合条件に使う。契約が異なる場合や応答形式が変わった場合は無消費扱いの生成を停止する。残量のフィールド名はAPIのまま表示する。応答に含まれる `usage.percent`・`usage.isNegative`・`usage.timeUntilNextPercent` も表示し、V5の無消費生成時に不足が示されていれば確認フラグにかかわらず止める。残量が正でも今回の生成に足りるとは限らず、契約照会だけでは全設定での0 Anlasや生成可能回数を判定しない。

## 設定・接続に問題があるとき

エラーと `--help` にも記入例を表示する。エラーには固定の読込元と状態だけを含め、秘密値・入力行・通信例外の本文は表示しない。

| 表示 | 意味と案内 |
| --- | --- |
| 設定不備：ファイルなし | 指定の設定ファイルがない。環境変数か `.secrets/novelai.env` のどちらかに設定する |
| 設定不備：設定行なし | ファイルはあるが `NOVELAI_API_KEY=` の行がない。トークンだけの記入でもこの案内になる |
| 設定不備：値が空 | 設定名はあるが右辺が空。トークンを記入する |
| 設定不備：形式不正 | 区切り・引用符・重複行・値の文字等に問題がある。表示された原因と記入例に沿って直す |
| 設定不備：読込失敗 | ファイルを読めない。アクセス権を確認する |
| 認証失敗：HTTP 401 | 読み込んだキーによる要求が認証されなかった。読込元とトークンの有効性を確認する |
| アクセス拒否：HTTP 403 | 接続先が要求を拒否した。キーの誤りと断定せず、アクセス権や接続制限を確認する |
| 通信障害 | キーの読込後に通信が完了しなかった。ネットワーク・プロキシ・実行環境の接続制限を確認する |
| サーバーエラー／API応答不正 | 接続先のエラーや想定外の応答。キー未設定とは区別して扱う |

空・未設定の読込元は従来どおり次の候補へ進む。有効なキーが見つからなかった場合に、各候補の状態を一覧表示する。値の形式が不正ならその読込元で停止する。ファイルの内容は自動で書き換えない。

通信障害だけを理由にキーの交換や再入力を勧めない。実行環境の接続制限が原因の可能性があるときは、その旨を説明して環境の許可手順に従う。制限外での再実行やブラウザー操作へ自動で切り替えない。契約照会の再実行と画像生成の再送は別であり、生成結果・消費が不明な要求を再送しない。

## １枚の生成を準備する

1. 作品の画風選択を済ませ、使用するモデル・sampler・機能を公式仕様で確認する。画風未選択の試験生成も行わない。
2. **要求JSONは原則として [標準スクリプト `novelai_compose.py`](#compose-standard) で作る。**手で書く場合は `config/novelai-request.example.json` を作品の `input/novelai-request.json` へコピーし、`input` にプロンプト、`model` に確認したモデルIDを設定する。samplerとscaleは採用モデルに合わせて見直す。例のモデル・プロンプトは空なので、そのまま送信できない。
3. 要求JSONに `width`・`height` を両方書いた場合はその寸法を使う（64以上の64の倍数）。コマ別の素材はコマより広い範囲を生成するため、ページ全体の生成希望寸法と違ってよい。書かない場合は [ページ設定](page-layout.md)に従い、`config/page-layout.json` の `generationCanvas` から補う。同梱枠の2000×3000pxは生成寸法の既定値ではない。2026-09-29のユーザー指示で、従来の「generationCanvasとの不一致で止める」動作から変更した。
4. steps未指定ならV5は23、それ以外は28。n_samplesは１枚に限定し、seedは未指定ならランダム（指定すれば固定。送った値は保存JSONと実行記録に残る）。V4・V5の `v4_prompt` と `v4_negative_prompt` が未指定なら、本文から人物別指定なしの構造を補う。人物別プロンプト等の指定済み構造は保持する。モデルごとの追加要件・samplerの互換性まではローカルで検証しない。

```powershell
python -X utf8 scripts/novelai_api.py generate --request input/novelai-request.json
```

この段階はキーを読まず通信もしない。寸法・steps・枚数・モデル・送信する要求全体のSHA-256を表示する。費用確認前に試験送信はしない。

漫画のコマ素材は、１コマ１要求のJSONを `input/novelai/requests/` に保存し、`scripts/novelai_batch.py` でページ単位・全ページを１枚ずつ順に生成する。検証・費用確認・実行記録・再送しない扱いはこの文書と同じ。使い方は [NovelAIでの制作手順](novelai-composed-production.md#batch)。公式APIの説明には人の操作を起点とする生成と過大な自動負荷の禁止が記載されているため、一括生成は人の指示で起動し、既定の送信間隔と件数の上限を保つ。この運用が利用条件に適合するかは未検証で、利用者が最新の規約を確認する。

<a id="compose-standard"></a>

## 標準スクリプト：novelai_compose.py（V5が既定、V4.5は指定時のみ）

NovelAI APIで生成する要求は、原則として作品の `scripts/novelai_compose.py` で組み立てる。モデルは**V5（既定 `nai-diffusion-5-curated`。Fullは書き込みが多くなり漫画に向かないため既定にしない）**。**V4.5（`nai-diffusion-4-5-curated`）はユーザーから指定があった場合だけ**使う。V4以前・V4.5 Fullは対応しない。ユーザー指示（2026-10-05）で採用した運用で、元は作品「NAIプロンプト検証」のフィードバック（FB-2026-10-05-novelai-ui-parity）で作成・検証されたスクリプト。

- **役割**：絵柄・背景・人物別の文・配置ピン・生成設定の引数から要求JSONを組み立て、`input/novelai/requests/<ID>.json` へ保存する。通信はしない。保存後に `novelai_batch.py generate` と同じ送信なし確認を表示する。送信・費用確認・実行記録・採用・組み直しは従来どおり `novelai_batch.py`（単発は `novelai_api.py`）が行い、`--execute` と費用確認フラグを渡したときだけ同じ処理へ引き継ぐ。
- **i2i・参照・その他の追加機能**：改造が必要な場合は、このスクリプトを元に改造して使う（V4.5の機能を含む）。追加する項目の書式・対応モデル・追加費用は、先に公式スキーマと [Opusの手順](ai-production.md#novelai-opus) で確認し、確認前に送信しない。改造しても、要求JSONの形式（`action`・`input`・`model`・`parameters`）と、`novelai_batch.py`・`novelai_api.py` の `generate` を通した送信（費用確認・実行記録）は保つ。画像入力の実装・費用は未検証のまま（下記「残る検証の単位」）で、t2iの一致結果を画像入力へ移さない。
- **使い方・引数・.envの補助設定**：[NovelAIでの制作手順](novelai-composed-production.md#compose)。
- **既定**：steps（V5は23、V4.5は28）は `novelai_api.py` と同じ。寸法は `--width`・`--height`、なければ `config/page-layout.json` の `generationCanvas`、未設定なら画面の既定832×1216。画面と同じ絵を再現するときだけ、画面の値を引数で渡す。

### 画面（Web UI）の生成と一致させる

同じ文でも、画面とAPIの絵が違うことがある。画面は入力に品質タグ・除外プリセット・Guidance・内部パラメーターを足して送るのに対し、APIは送った内容だけを使うため。作品「NAIプロンプト検証」（配布版0.5.0）で、画面で生成したPNGのメタデータ（`Comment`・`Description`・`Source`）を正として比較し、次を観察した。**条件付きで再現**であり、普遍的な仕様ではない。

| 観察（2026-10-05） | 内容 | 状態 |
| --- | --- | --- |
| 画面との差の例（V5 Curated） | 本文末尾に `, very aesthetic, masterpiece, no text` が自動で付く。除外はHeavyプリセット＋入力。Guidance 7.0。人物別本文の先頭は `girl`（`1girl` ではない）。`use_coords` は配置ピンなし | 1回のAPI生成と画面PNGの突合せ |
| 内部パラメーター | 画面PNGは `deliberate_euler_ancestral_bug: false`・`prefer_brownian: true`。省略したAPI要求のPNGは逆（true／false）だった。単独の効果は未分離なので、明示指定する | 観察。効果は未検証 |
| 配置ピンなしでも `centers` は影響する | `use_coords: false` でも、`centers` の値を画面の履歴と同じにしないと絵が変わった（2人目 0.5 → 0.3 で一致） | 1例 |
| `tag_hint_qt`・`tag_hint_uc_preset` | 送らなくても全画素一致 | V5で確認 |
| V5 FullとCurated | モデルハッシュと除外プリセットだけ違う（Fullの画面は除外の先頭に `nsfw, `）。品質タグ・Guidance 7.0・パラメーターは同じ | 各1回 |
| V4.5 Curated | 画面の品質タグは `very aesthetic, masterpiece, no text, -0.8::feet::, rating:general`、除外Heavyに `dithering`・`screentone` がない。公式文書の記載と違い、画面を正にして一致 | 1回 |
| Guidanceの画面の既定 | V5は7.0、V4.5 Curatedは5.0（利用者の画面の表示値。画面の既定か利用者の設定かは区別できない） | 観察 |

- **一致を確認した範囲**：V5 Curated・V5 Full・V4.5 Curatedの各1回、832×1216・23steps・人物2人・配置ピンなし・参照なし。2枚のPNGをRGBへ変換した全画素差で比較した。別の入力・寸法、配置ピンあり、同条件の再現性（複数回の同一画素）、V4.5の配置ピンの5×5マスへの寄せは未確認。
- **方針**：品質タグ・除外プリセットは公式文書だけを根拠にせず、画面PNGの記録と照合する。画面と同じにしたいときは、画面のPNGメタデータ（`Comment`）の入力文・人物別文・座標・Seed・寸法・steps・samplerを `novelai_compose.py` の引数へ写す。画面のFullの `nsfw, ` は、ユーザー指示によりスクリプトが除外へ足さない（完全に同じにするには `--uc-preset-text` へ全文を渡す）。V4.5のlight・human、V5 Fullのlight・humanの除外プリセットは画面PNGがなく未確認。
- **限界**：出典の確認日は作品側の調査日（2026-10-05）で、キットへの取り込み時に公式文書・画面を再取得していない。PNGに残るのは生成設定で、HTTPヘッダーや通信形式（画面は `stream: msgpack`）は復元できない。確認できたのは出力画素の一致だけで、送信形式まで画面と同じとは言えない。モデル・画面の既定は更新されるため、送信直前に公式文書と画面で再確認する。Anlasの実消費は未計測（`actualAnlasCost` は `null`）で、無消費の保証ではない。

### 実際に送った内容の保存

送信のたびに、候補PNGの隣へ `rNNN.request-body.json`（送信バイトそのもの）と `rNNN.request.json`（同じ内容の整形版）を保存し、実行記録の `sentRequestFiles` へ保存先を残す。`rNNN.request.json` は要求JSONと同じ形式なので、`input/novelai/requests/` へコピーして編集し、再生成の元にできる。画面のPNGのメタデータとの突き合わせにも使う。キーは含まない。

<a id="position-pins"></a>

## 配置ピンの要求

NovelAIで画面内の人物・物の位置を指定する場合だけ使う。UIの使い方・使用判断・モデルによる違いは [配置ピンの制作手順](novelai-composed-production.md#position-pins) を参照する。

公式画像APIスキーマで `parameters.v4_prompt` の `use_coords`・`use_order`（真偽値）、`caption.char_captions` 内の `char_caption`（文字列）・`centers`（`x`・`y` の数値を持つオブジェクトの配列）を確認した。V5でもこのフィールド名を使う既存実装で、指定済み構造は `novelai_api.py` が保持する。独自のトップレベル `position` やプロンプト内のピン番号で置き換えない。

以下は `parameters.v4_prompt` の構造例であり、送信できる要求全体ではない。例の本文を `input` と一致させ、画風・除外文・モデル・生成寸法等は作品の採用設定に合わせる。

```json
{
  "caption": {
    "base_caption": "2girls, standing side by side, full body, outdoors",
    "char_captions": [
      {"char_caption": "girl, short black hair, blue jacket, on the left",
       "centers": [{"x": 0.3, "y": 0.5}]},
      {"char_caption": "girl, long brown hair, red jacket, on the right",
       "centers": [{"x": 0.7, "y": 0.5}]}
    ]
  },
  "use_coords": true,
  "use_order": true
}
```

例は生成素材内の左上を原点とし、右・下へ増える0〜1の正規化座標を想定した検証候補（V5用）。ページ内のピクセル座標や組版の `focus` と混同しない。今回確認した公式スキーマは `x`・`y` の型だけを示し、座標の範囲・原点・V4／V4.5の5×5グリッドとの数値対応は記載していない。その意味と実受理は使用モデルで別途確認し、未確認の換算を公式仕様として断定しない。

比較時は本文・人物別本文・Seed等を同じにし、`use_coords` を切り替える案を使える。自動配置へ戻す要求では `use_coords: false` を明示する。**`use_coords: false` でも `centers` の値は絵に影響した例がある**（上記、画面との一致の観察）。座標を固定して比べるときは `centers` も揃える。人物別入力・文字と枠の除外は保持し、`v4_negative_prompt` を指定する場合も対応する人物と順序を照合する。配置ピンは専用の画像参照とは別の機能で、ピンの使用を理由に参照画像を追加しない。

出典・取得日：2026-10-04、[NovelAI公式画像APIスキーマ](https://image.novelai.net/docs/doc.json) の `image.V4ConditionInput`・`image.V4ExternalCharacterCaption`・`image.Coordinates`。確認したのは書式とローカル実装の読み取りで、API送信・生成効果・座標解釈・費用は未検証。生成前には従来どおり全設定の費用と利用枠を確認する。

## 確認後に生成する

有効なOpus契約で、**今回の要求の全設定が0 Anlasであることを実際に確認した場合だけ** `--confirm-zero-anlas` を付ける。これは人または確認手段から得た結果の宣言であり、サーバーへ無課金を強制する機能ではない。[Opusの条件](ai-production.md#novelai-opus)に従い、APIでの適用を確認できない場合も止める。

```powershell
python -X utf8 scripts/novelai_api.py generate --request input/novelai-request.json --output output/novelai/test-001.png --execute --confirm-zero-anlas --cost-note '今回の全設定について確認した方法・日時を記入'
```

V5では今回の要求を実行できる利用上限を確認した上で `--confirm-v5-allowance` も必要。足りない場合は待つ。フラグは確認済みに見せるために付けない。

無消費扱いでは28steps以下・1,048,576画素以下・１枚・テキスト生成を候補範囲とし、参照・アップスケール・未知のパラメーターを拒否する（`novelai_compose.py` が画面と同じ値で送る `controlnet_strength: 1.0` だけは通常の生成として扱う）。この範囲内というだけで0 Anlasを保証しない。費用が不明なら送信しない。

ユーザーが**今回の設定でAnlasを消費することを明示指示した場合だけ** `--confirm-zero-anlas` の代わりに `--allow-anlas` を使い、`--cost-note` に確認した費用と許可範囲を記す。キーの設定、接続確認や生成の依頼だけでは有料利用の許可とみなさない。各実行に `--allow-anlas` と `--cost-note` を付けて記録する。API料金の自動見積り・支払上限の強制・参照素材の自動エンコードは未実装。参照機能等は公式形式に整えた要求と費用確認が別途必要。

保存先は作品の `output/` 内のPNGだけ。生成要求・費用確認の根拠・確認日時・要求SHA-256・６文字の照会ID・生成実寸を隣の `.novelai.json` へ記録する。キーは記録しない。生成要求と元PNGは作品の制作資料であり、公開時は従来どおりメタ情報を除去する。元PNGの実寸と希望寸法を区別し、[枠配置・最終PNG](page-layout.md)へ反映する。Anlasの実消費を自動測定していないため、`actualAnlasCost` は `null` とする。

契約照会（`/user/subscription`）は、生成のたびには呼ばない。最初の生成（おためし）で呼び、以後は前回の照会から数えて10回の生成ごとに1回にする（ユーザー指示、2026-10-05。API呼び出しが多すぎることによる警告のリスクを減らすため。回数は目安）。間の生成は前回の結果を使い、`output/novelai/subscription-check.json` にカウントを保存する。モデル・寸法・steps・枚数・追加機能の変更、前回の生成が完了を確認できていない場合、V5の利用上限の残量が少ない場合（`percent` が3以下、または不足を示した場合。3はユーザー指定の閾値）は、回数にかかわらず照会する。照会を強制するにはこのファイルを削除する。`status` は常に照会する。この間引きは契約照会の呼び出し回数だけで、有料利用の許可・費用確認フラグ・停止条件は変えない。詳細は [Opusの手順](ai-production.md#novelai-opus) の3番。

送信前に実行記録を作成し、同名画像・記録があれば止める。HTTPエラー、タイムアウト、保存失敗を自動再送しない。失敗時は記録とNovelAI側の結果・消費を先に確認する。別の名前への変更も再送に当たるため、結果不明のまま繰り返さない。PNGはZIPまたはJSON/base64から取り出し、チャンク構造・CRCと実寸を確認する。画像の見た目の確認は別途必要。

## 確認を依頼するプロンプト

キーを用意し、作品フォルダをCodexで開き直してから使用する。

```text
このプロジェクトのNovelAI接続を確認してください。
AGENTS.md、docs/SETUP.md、docs/knowledge/novelai-api.mdを読んでください。
キーは環境変数または.secrets/novelai.envに用意します。
秘密ファイルの本文やキーの実値は表示しないでください。
scripts/novelai_api.pyのkey-status、続いてstatusを実行し、
キーの読込元、契約照会の成否、不足している設定を教えてください。
今回は画像生成とAnlas消費を許可しません。ブラウザーは操作しないでください。
```

接続確認後に生成まで確認する場合の追加依頼例：

```text
NovelAIでテスト画像を１枚生成できる状態まで準備してください。
画風・モデル・生成希望寸法の指定が未確定なら確認してください。
input/novelai-request.jsonとページ設定を整え、送信なしの要求確認を実行してください。
今回の全設定で0 Anlasを確認でき、V5なら利用上限も足りる場合だけ、
１回生成してoutput/novelai/test-001.pngを提示してください。
費用や残枠が確認できない場合は送信せず、未確認事項を教えてください。
有料利用と失敗時の自動再送は許可しません。
```

## 出典・確認範囲

確認日：2026-09-21。確認事実は [NovelAI公式画像APIスキーマ](https://image.novelai.net/docs/doc.json) に記載されたPersistent API token認証、`/user/subscription`、`/ai/generate-image`、生成パラメーター、JSON/base64・ZIP応答、照会IDの形式。スキーマの `basePath` は `/`、hostは未指定のため、この実装ではスキーマ提供元の `https://image.novelai.net` に接続先を固定する。リダイレクトへ認証ヘッダーを転送しない。

既定値・保存規則・費用確認フラグはキットの実装方針。実際の契約での接続、各モデルの生成、APIでの0 Anlas適用、V5残枠、生成品質は未検証。公式スキーマの取得と実APIでの動作確認を区別し、確認結果は作品の通常の進捗記録へ残す。

### 残る検証の単位

2026-09-26のフィードバック取り込みでは、NAI-VERIFY-01をキットの非公開作業計画に登録した。現行仕様と接続、費用・使用枠、最小の実API往復、対応する画像入力、コマ別制作の比較、確認結果の文書反映を分けて扱う。実施条件・進行状況は作業計画、接続・料金の確認結果はこの文書を正本とする。作品への配布物だけでは検証済みと判断しない。

初期画像i2i、外見・画風の専用参照、複数画像入力は、対象モデルの実スキーマ・枚数・強度・前処理・追加費用をそれぞれ確認する。UIの機能名からAPI対応を推測せず、t2i成功をi2iの検証完了に数えない。無消費扱いのt2i候補条件を画像入力へ流用しない。

コマ比較は [外部画像生成の共通手順](external-panel-i2i.md) へ接続するが、NovelAIでの同等効果は未検証。完了の根拠には実施日・モデル・環境・対応入力・要求設定・許可と費用の根拠・実結果と原画・失敗と限界・反映先が必要。未対応は対象と根拠を残し、未実施・費用不明の機能は残項目にする。タスク登録をAPI送信やAnlas消費の許可にはしない。
