# PixAI素材生成＋Codex組版の標準手順

PixAIで漫画制作を始めるときに読む。APIの仕様・費用確認・送信の記録は [PixAI APIの接続手順](pixai-api.md)、各機能の受理と効果は [実生成での確認結果](pixai-api.md#results)。生成条件はモデルとAPIの版で変わるため送信直前に再確認する。**LoRA の効果は未確認。**

**人物の一貫性の保ち方（制作提案）**：今回観察した条件では、外見を毎回同じ語で書く v2（Tsubaki.2）で特徴を保ちやすかった。これを第一候補とし、利用者の依頼がある場合だけ `.env.pixai` の変数にする。参照画像だけで作る場合は、Tsubaki.2 に IP-Adapter と短い色の補助（`navy blue and red` 等）を組み合わせ、除外に `sepia, yellow tint` を足すと色かぶりを抑えられる。Haruka v2 の IP-Adapter は意匠を強く写すが、色かぶりとプロンプトの無視が出やすいため、人物試作・決めの１枚に限る。

## 制作開始と画風

1. 作品のOPTION、既存の画風指定、`config/pixai-production-policy.json` を確認する。作品固有の指示を優先する。
2. **モデルを決める。** 既定は Tsubaki.2（DiT。プロンプトの理解・人体・複数人物の描写が強いと公式が説明）。安定した塗りと手を重視するなら Haruka v2、日本で人気の作風なら Hoshino v2（どちらもSDXL）。PixAIの公式モデル15種は `config/pixai-models.json` に収録済みで、`--model <名前>` で選ぶだけで使える（バージョンIDを調べない。一覧は `python -X utf8 scripts/pixai_models.py list`、[一覧と特徴](pixai-api.md#models)）。Tsubaki.3（`--model tsubaki3`）は既定の mode が `pro`（`standard`・`lite` は拒否）で、１枚1分以上かかる（[確認結果](pixai-api.md#results)）。利用者が一覧にないモデルを指定したら、モデルページのURLをもらって `python -X utf8 scripts/pixai_models.py add <名前> --url <URL>` で作品の一覧へ登録する（キー・クレジットを使わない）。登録時に表示される利用条件（商用・オンライン共有）を利用者に伝え、公開の可否を確かめてもらう。読めない場合は版のタブを押したURLを写してもらい `--model-version-id` と `--model-type` で指定する。
3. **画風を決める。** Tsubaki.2・Tsubaki.3 系では公式の画風プリセット（`--style-preset`。35種。一覧は `python -X utf8 scripts/pixai_compose.py --list-styles`）か、画風の文（`--style`）を使う。SDXLのモデルではプリセットは無視されるため、画風の文と画風LoRAで決める。画風が未指定なら、利用者にモデル・プリセット名の候補から選んでもらい、選択を待ってから作画する。モデルと画風プリセットの絵柄の違いは、キット側の `resources/pixai-model-samples/index.html`（公式モデル15種と、Tsubaki.2 での画風プリセット35種を、基本的に同じプロンプトで各１枚）で見比べられる。案内するときは、`project.json` の `sourceKitRelativePath` から解決して実在を確かめた絶対パスだけを示す（見本画像は作品へコピーしない）。見本を作り直す生成はクレジットを使うため、明示の許可がある場合だけ。特定作家・漫画家の名前は使わない。画風プリセット `flat-anime-pastel`（Pastel Flat）は、プロンプトにない**頭の上の輪**（既存作品を連想させる意匠）を描きやすい。除外に `halo` を入れても出る。公開作品では使わないか、出た輪を `pixai_edit.py inpaint --no-style`（Tsubaki.3 で描き直す）で消して確認する。
4. 採用したモデル・画風・除外文・人物外見文・LoRA・主要生成設定（縦横比・解像度・mode）を共通化し、コマごとに動作・画角・背景だけを変える。seedだけで一貫性は保証しない。

## PixAIで使える表現の幅（このキットで扱う機能）

| 機能 | 使いどころ | 状態 |
| --- | --- | --- |
| **キャラクターLoRA**（v2 の `loras`、最大5件） | 作品の人物の顔・髪・服を全コマで揃える。PixAIのモデルマーケットで公開・作成したキャラクターLoRAのバージョンIDを `.env.pixai` の `PIXAI_LORA_…` に置き、要求から `${PIXAI_LORA_MIO}` で参照する。重みは0〜1（既定1）。トリガー語は省略時にモデルの既定が使われる。使う前に `python -X utf8 scripts/pixai_models.py lora --url <LoRAのページ>` で元モデル・利用条件を作品の `config/pixai-loras.json` に記録する（１回だけ。記録済みは取り直さない）。送信前の確認で、生成モデルと元モデルの種類が違えば注意を表示する | 公式文書で確認。効果は未検証 |
| **画風LoRA** | 作品全体の線・塗りを揃える。キャラクターLoRAと合わせて最大5件 | 同上 |
| **画風プリセット**（`style`） | Tsubaki.2・Tsubaki.3 系で、線・塗りの方向を１語で切り替える（`hard-line-monochrome-accent`、`pencil-sketch`、`retro-tv-anime` 等） | 公式文書で確認。SDXLでは無視 |
| **mode**（lite・standard・pro・ultra） | Tsubaki.2・Tsubaki.3 系の品質と速さの段階。Tsubaki.2 は4種とも受理（pro・ultra は塗りが柔らかい暖色になる）。Tsubaki.3 は pro・ultra だけ（standard・lite は拒否）。費用の差は未確認 | 公式文書・[実生成](pixai-api.md#unverified-results)で確認 |
| **縦横比 11種・1.5k** | 横長・縦長のコマに合わせた素材。1:3・3:1 は縦長・横長の帯状のコマに使える | 公式文書で確認 |
| **batchSize 4** | １タスクで4枚の候補を作り、見比べて採用する。**複雑なコマ（２人以上・インペイント）と作り直しでは基本にする**（下の「枚数と費用」） | 受理を確認。費用は下の「[枚数と費用](#batch-size)」 |
| **Hires Fix**（v1 の `upscale`）・**ADetailer**（v1 の `enableADetailer`） | 決めゴマの解像度を上げる（1.5倍で1272×1920。描き込みが細かくなる）。ADetailer の効果は小さい | 公式文書・[実生成](pixai-api.md#unverified-results)で確認 |
| **i2i**（v1 の `mediaFile`＋`strength`） | ラフ・前のコマの絵・修正版を元に描き直す。strength 0.6 で構図を保った小さな変更、0.9 で構図・ポーズを保った大きな変更（Haruka v2） | 公式文書にない項目。[受理と効果を確認](pixai-api.md#unverified-results)。`--allow-unverified` |
| **インペイント**（v1 の `--i2i`＋`--mask`） | 一部だけ描き直す（小物の差し替え・描き足し・消去）。マスクの外は保たれる（[インペイント](#inpaint)） | 公式文書にない項目。[受理と効果を確認](pixai-api.md#unverified-results)。`--allow-unverified` |
| **latentCouple**（v1、領域ごとのプロンプト） | 左右の人物の髪・服を描き分ける（SDXL）。ただし人数が増えることがある | 公式文書にない項目。SDXLで効果を確認、人数の問題は未解決。`--allow-unverified` |
| **ControlNet**（v1 の `controlNets`） | 元画像の構図を写す。普通の絵からは canny（線・形）と depth（奥行き）が効く。openpose は普通の絵ではポーズとして効かず、scribble は failed になる。SDXL（haruka2 等）で使う（Tsubaki.2 等は非対応） | 公式文書にない項目。[canny・depth の効果を確認](pixai-api.md#unverified-results)。`--allow-unverified` |
| **IP-Adapter**（v1 の `ipAdapter.referenceFiles`） | **キャラクター・画風の参照画像**。LoRAのない人物を、人物試作の採用画像に似せる | 公式文書にない項目。受理を確認。`--allow-unverified`。公式の「PixAI Reference Pro」はAPI未対応 |

公式文書にない機能（i2i・インペイント・ControlNet・latentCouple・IP-Adapter）は、受理と効果を[確認済み](pixai-api.md#unverified-results)のものも含め、予告なく変わる可能性がある。利用者が使うことを了承した場合だけ使い（`--allow-unverified`）、１コマで試して画像を開いて確認してから広げる。結果（受理されたか、効果、クレジット）は作品の `docs/production/PIXAI-BATCH.md` に残す。公式文書にない機能を使ったというだけで一致・品質向上を扱わない。

## 素材生成と組版

Codexでコマ割りと読み順を設計し、PixAIは文字・枠のない組版用イラストに使う。全身や周囲の余白を残しやすい構図で生成し、配置時に回転・拡大・部分表示する。見せたい接点・顔・手と、文字を置く余地を生成前に決める。画像条件付きのコマ作画（i2i・ControlNet・参照画像）を選んだ場合は `manga-external-panel-i2i` と [共通手順](external-panel-i2i.md) を併用する。

### 本番前の人物試作

コマの生成へ進む前に、主要人物ごとに人物試作を生成する（`--id chara-mio` 等。`batchSize 4` で候補を見比べてもよい）。字コンテやキャラ設定の外見（髪の長さ・色、眼鏡、上着と制服の重ね順、小物の左右）と照合し、ずれがあれば外見文・LoRAの重みを直してから本番へ進む。採用した試作画像は、IP-Adapterの参照画像（公式文書にない機能。受理は確認済み）にも使える。試作と修正内容は制作記録へ残す。

### 生成寸法と配置

PixAIのv2は画素数ではなく**縦横比と解像度の段階**で寸法を決める（[対応表](pixai-api.md#公式仕様確認した事実)）。コマ別の素材は**コマより広い範囲**を生成し、ページではコマ枠とマスクで必要な部分だけを見せる。

- 縦横比はコマの形に近いものを選ぶ（横長のコマは `3:2`・`16:9`、縦長は `2:3`・`9:16`、帯状は `1:3`・`3:1`）。`pixai_compose.py` は `--aspect-ratio` がなければ `config/page-layout.json` の `generationCanvas` に最も近い比を選ぶ。例は `config/pixai-production-policy.json` の `panel_aspect_examples`。
- 生成の実寸（例：`2:3` の `1k` は 848×1280px）は実行記録に残る。ページ全体を１枚で生成する場合も、実寸に枠と最終PNGを合わせる（[ページ設定](page-layout.md)）。
- コマ内の見せ方はページ構成JSONの `focus`（画像内でコマの中心に置く点）・`zoom`・`rotation` で指定する。空間を見せる引きのコマを大きく拡大して一部だけ見せると空間が消えるため、引きの構図そのものを生成し直す。

<a id="prompt-writing"></a>

### 要求プロンプトの組み立て

字コンテのコマを、画像に**見える形**の語へ置き換えてから書く。PixAIのモデルはDanbooru系のタグとプロンプトを読む（公式の例文：`1girl, green hair, masterpiece, best quality, solo, standing, flower`）。以下はキットの制作提案で、PixAIでの効果は未検証。

1. **順番**：人数と主対象（`1girl, solo` / `no humans`）→ 人物の外見 → 見える姿勢・動作・表情 → 画角・被写体の大きさ・画面内の位置 → 場所の目印 → 時間・光 → 画風 → 品質タグ。`pixai_compose.py` はこの順で連結する。
2. **強調は丸括弧だけ**：`(smile:1.2)` のように書く。角括弧・波括弧、NovelAI形式の `1.2::word::` は使えない（v1 の公式説明。`generate` が警告する）。
3. **否定語を肯定側に書かない**：`not smiling`、`no people`、`without glasses` はその語に反応して逆に出ることがある。避けたい要素は `negativePrompt` に書く。人物なしは `no humans` のタグを使う。
4. **意図ではなく見える形、途中ではなく状態を書く**：`about to sigh` ではなく `eyes half closed, shoulders dropped, looking aside`。`unfolding a paper airplane` ではなく `an unfolded sheet of paper with fold creases, held open in both hands`。
5. **部分のアップは誰の体かを書く**：`1boy, lower body, standing, school shoes, a paper airplane on the ground at his feet`、`1girl, hands only, …`。
6. **２人のコマ**：PixAIには人物別の入力・配置ピンがない。まず１人ずつのコマに分けられないかを検討する（相手は画面外・肩越しなど）。２人を同時に描く場合は、姿勢と位置関係（`sitting side by side, girl on the left, boy on the right, facing each other`）を外見より前に書き、外見は識別に必要な最小限にする。Tsubaki.2 は複数人物の描写が強化されていると公式が説明しているが、取り違えは画像で確かめる。キャラクターLoRAを２人分使う場合も、外見が混ざらないか確認する。
7. **画角は字コンテから選ぶ**：`from above`・`from below`・`from behind` は候補であり、全コマの先頭に付ける決まりではない。同じ画角が３コマ続くと `generate` が警告する。
8. **識別の特徴を要求ごとに書く**：人物の特徴（髪の色と長さ、眼鏡の形、服の重ね順、小物）を毎回同じ語で書く。LoRAを使う場合も、コマで見せたい服・小物は文で書く。特徴を `input/pixai/characters.json` に登録し、要求ごとの登場人物を `cast` に書くと、`PIXAI_CHECK_IDENTITY=1` のときだけ `generate` が抜けを警告する（形式は下の例。点検は語の検出で、画像認識ではない）。
9. **数値の年齢や man・woman を入れない**：数値の年齢は見た目に効きにくく、`man`・`woman` は別の人物が増えることがある。`teenage`、`high school student`、`adult` は使ってよい。
10. **promptHelper は使わない**：PixAIの公式の既定は、送信前にプロンプトを自動で書き換える `enable`。字コンテとの照合を保つため、このキットの既定は `disable`。使う場合は理由を記録する（`generate` が警告する）。

```json
{
  "characters": {
    "mio": {"name_ja": "日向ミオ", "features": {
      "hair": "light brown short bob hair", "outer": "open yellow hoodie worn over navy blazer"}}
  },
  "cast": {"p01-01": {"mio": "all"}, "p01-03": {"mio": ["outer"]}}
}
```

### 場面の関係と継続状態を各要求へ展開する

人物・物の名称だけを並べず、字コンテを次の順で各コマの見える状態へ展開してから要求を書く。

1. **その瞬間の関係を確定する**：主対象と、誰が何に対して何をしているか。必要な接点・所持・操作、行為者と相手、姿勢、身体の向き、視線の先、読者から見た左右・上下を日本語で具体化し、そのコマを別の行為と区別する条件を1～3項目に絞る。
2. **直前から続く状態を引き継ぐ**：服と色、持ち物、持つ手、姿勢・向き、人物の左右・距離を確認する。変化が指定された項目だけ更新し、このコマに見える継続状態は要求へ再記述する（前コマの要求は今回の生成へ伝わらない）。
3. **１つのプロンプトへ主語を明記して統合する**：PixAIには人物別の入力がないため、`girl on the left holding an open notebook toward the boy, boy on the right looking down at the notebook` のように、誰が何をするかを主語付きで書く。人物なしのコマへ人物の語を入れない。

**セリフ・文字・吹き出しはPixAIへ渡さない。** セリフ本文、`speech bubble`・`japanese text` 等の肯定指定をプロンプトへ入れない。枠も生成させない。除外文には `text, speech bubble, panel border, watermark` 等を使う。`pixai_compose.py` は `.env.pixai` の `PIXAI_NEGATIVE_PROMPT` が未設定ならこの４語を既定で付ける（設定すれば全要求の既定を置き換える）。セリフ・画中の文字・効果音は組版指定に残す。

<a id="prompt-content-check"></a>

### 送信前の内容照合

`manga-ai-production` でプロンプトを作成・点検するときは、変数展開後のプロンプト・除外・LoRA・参照画像を一緒に読み、字コンテと照合する。記録は [PixAI一括生成の記録](../production/PIXAI-BATCH.md) へまとめる。

| 確認 | 判定する内容 |
| --- | --- |
| 関係 | 主対象、行為者・相手、必要な接点・所持・操作が、送信する文から判別できるか |
| 継続状態 | 直前から変わらない服・持ち物・手・向き・位置が今回の要求にも残っているか |
| 割り当てと矛盾 | 主語と外見・動作が対応するか。LoRA・参照画像の人物と、プロンプトの人物が一致するか |
| 文字の分離 | 文字や吹き出しの肯定指定がなく、除外指定と後からの組版指定があるか |

`pixai_batch.py generate` は送信前に否定語・意図の表現・数値の年齢・体の部分・２人以上・括弧の書式・promptHelper・画角の連続を点検し、警告を表示する。警告が残る要求は、プロンプトを直すか、残す理由を記録してから `--accept-warnings` を付けて送信する。点検は語の検出であり、内容照合の代わりにならない。

<a id="batch"></a>

### 要求JSON・一括生成・採用・組み直し（人間が再実施できる形）

人間がページ単位・全ページで何度か生成し直し、採用する画像を選んでから続きを進められるように、要求と構成をすべてファイルに残し、同梱の `scripts/pixai_batch.py` で生成・採用・組み直しを行う。

| 置き場所 | 内容 |
| --- | --- |
| `input/pixai/requests/p01-03.json` | １コマ１要求のJSON（[形式](pixai-api.md#要求jsonの形)）。ファイル名は `p{ページ2桁}-{コマ2桁}`、差し替え案は `p01-03b.json`、人物試作は `chara-mio.json` 等 |
| `output/pixai/candidates/p01-03/r001.png` | 生成候補。実行ごとに番号が増え、上書きしない。隣に実行記録 `.pixai.json`（taskId・送信内容・費用確認の根拠）。batchSize 4 は `r001`〜`r004` |
| `input/pixai/adopted.json` | 採用した候補（`adopt` で記録） |
| `input/typeset/page-01.json` | 組版指定（フキダシ・文字・画中の文字・文字を置かない範囲）。形式は [組版スクリプト](japanese-manga-readability.md#typeset-script) |
| `input/pages/page-01.json` | ページ構成：`layout.json`、組版指定、コマごとの採用画像（`request` は `input/pixai/adopted.json` を引く。ファイル直接は `source`）と `focus`・`zoom`・`rotation`、効果音等の `overlays` |
| `output/build/page-01/v001/` | 組み直しの結果。版ごとに新しいフォルダ。`page-01.png`、指定時は `page-01.psd`、`build.json`、組版の点検結果 |

```json
{
  "schema_version": 1,
  "layout": "output/layout/page-001-v1/layout.json",
  "typeset": "input/typeset/page-01.json",
  "panels": [
    {"panel": 1, "request": "p01-01", "focus": [0.5, 0.4]},
    {"panel": 2, "request": "p01-02", "focus": [0.5, 0.5], "zoom": 1.1},
    {"panel": 3, "source": "output/fixed/p01-03-fix.png", "original_source": "output/pixai/candidates/p01-03/r002.png"}
  ],
  "overlays": [{"name": "効果音 パタ", "source": "templates/onomatopoeia/images/burst-pata.webp", "center": [700, 1300], "scale": 0.6, "rotation": -10}]
}
```

```powershell
# 送信せずに内容・寸法・seed・アップロード予定を確認
python -X utf8 scripts/pixai_batch.py generate --page 1
# 1ページ分を１タスクずつ順に生成（全ページは --all、特定コマは --ids p01-02,p01-04）
python -X utf8 scripts/pixai_batch.py generate --page 1 --execute --accept-warnings --confirm-credits --cost-note '確認した残高・許可範囲・日時'
# 完了待ちが途切れた記録を取得し直す（生成は再送しない）
python -X utf8 scripts/pixai_batch.py fetch --page 1
# 候補を見比べて採用
python -X utf8 scripts/pixai_batch.py list --page 1
python -X utf8 scripts/pixai_batch.py adopt p01-02 --candidate 3
python -X utf8 scripts/pixai_batch.py adopt-latest --page 1
# 同じページ・コマ・配置で組み直す（PSDも作るときは --write-psd）
python -X utf8 scripts/pixai_batch.py build --page 1
```

- `generate` は初回は要求のseed、２回目以降は乱数のseedを使う（`--seed request` で固定。v1 の要求で seed を書いていない場合は乱数を足さない）。１タスクずつ送信して完了を待ち、送信間隔は既定３秒、１回の上限は既定30タスク。**費用確認・公式文書にない項目は１件目を送る前に全件で確かめる。** 失敗したら残りを送らずに止まり、自動再送しない。
- 完了待ちの既定は１タスク900秒（`--timeout`）。Tsubaki.3 の pro のように１枚で1分以上かかるモデルでは、複数タスクの `generate` が合計で実行環境のコマンド待機時間を超えることがあるため、その環境の継続実行の仕組みを使い、ログ（例：`output/pixai/gen-p1.log`）で進み具合を確かめる。途切れた記録は `fetch` で取得し直す。
- 画像のない実行記録があるコマは再生成しない。taskId があれば `fetch` で取得し直す。ない場合はPixAIの画面で生成とクレジットを確認し、`move-unknown --ids <要求ID> --confirm-checked --note '確認した内容'` で `failed/` へ移す。タスクが作られなかった（HTTP 4xx）・failed・cancelled の記録はスクリプトが自動で `failed/` へ移す。
- `adopt-latest` は対象の各フォルダの最大番号のPNGを採用する。新しい生成が失敗したコマは以前の最大番号が選ばれるため、生成結果と画像を確認する。
- `build` は採用画像が未選択なら止まる。NovelAI等の他の手段で作った画像を同じページに置くコマは、`request` ではなく `source` にパスを書く。
- 要求の書き方を比べるときは、差し替え案（`p01-03b.json` 等）と同じ seed で `--seed request` を使い、変えた語以外の設定を揃える。対照が成功していない組から結論しない。
- 人間が画面で操作したい場合は `.agents/skills/pixai-batch-webui/SKILL.md` に従ってWebUIを起動し、URLだけを案内する（ブラウザーは起動しない）。
- Codexは最初の作画でもこの手順を使い、各ページのコマンドを [PixAI一括生成の記録](../production/PIXAI-BATCH.md) に残す。ユーザーに見せるPNGは `build` の出力を使う。

<a id="batch-size"></a>

### 枚数と費用（batchSize 4 を基本にする場面）

**複雑なコマ（２人以上の人物・インペイント）と作り直し（候補があるコマの再生成）は、１タスク4枚（`batchSize` 4）で生成し、4枚を見比べて採用する。** Tsubaki.3 pro 1k では1枚4,000クレジット、4枚7,000クレジット（1枚あたり1,750）で、1枚ずつ2回試すより安い（利用者がPixAIの利用履歴で確認）。他のモデルの目安は [費用](pixai-api.md#costs)。

- `pixai_compose.py` は、２人以上・`--mask`（インペイント）・候補があるIDで `batchSize` 4 を既定にする（`--batch-size 1` で1枚）。
- `pixai_batch.py generate` は、候補があるコマ（作り直し）を4枚で送る（`--batch-size auto` が既定。`--batch-size 1`・`4` で指定）。送信なしの確認の「合計：Nタスク・M枚」で枚数を確かめ、利用者の許可範囲に4枚分が含まれることを確認する。
- １人の単純なコマの初回は1枚でよい。
- 4枚は `r005`〜`r008` のように連番で保存され、WebUIでは「同じ生成の4枚」としてまとめて表示し、その中から採用できる。

<a id="inpaint"></a>

### インペイント・i2i（生成済みのコマを直す。`scripts/pixai_edit.py`）

採用画像（または候補）を元に、**インペイント**（マスクの範囲だけ描き直す）か **i2i**（全体を描き直す）の要求を作る。元の要求のプロンプト・除外・モデル・画風プリセット・mode・LoRA・seed を引き継ぎ、直したい内容（`--add`）をプロンプトの先頭に足して、差し替え案のID（`p04-01b` 等）で保存する。元の要求と候補は変えない。通信しない。

```powershell
# 一部だけ直す：マスク（白＝描き直す）と確認用の重ね画像 input/pixai/masks/<ID>.preview.png も作る。既定で4枚
python -X utf8 scripts/pixai_edit.py inpaint p04-01 --add "girl with cat ears on top of head" --ellipse 300,40,260,180
# 全体を描き直す：strength 0.6 は構図を保った小さな変更、0.9 は構図・ポーズを保った大きな変更（Haruka v2 の例）
python -X utf8 scripts/pixai_edit.py i2i p04-01 --add "snowy park, winter, snow" --strength 0.6
# 送信なしの確認 → 送信（公式文書にない項目のため --allow-unverified が必要）
python -X utf8 scripts/pixai_batch.py generate --ids p04-01b
# 採用（描き直した範囲を元の解像度で元画像と並べて確かめてから、元のコマに差し替え案の画像を採用する）
python -X utf8 scripts/pixai_batch.py adopt p04-01 --file output/pixai/candidates/p04-01b/r002.png
```

- 元画像は採用画像（既定）、なければ最新の候補。`--candidate N` で番号を指定する。v1 の寸法（512〜1280px）に入らない 1.5k の画像は直せない。
- インペイントに非対応のモデル（Tsubaki.2。`config/pixai-models.json` の `inpaint: false`）の画像は、`--model` を省くと Tsubaki.3 で描き直す。背景・小物ならなじむ（輪を消す課題で4枚中3枚成功）。
- 画風プリセットが直したい物の原因のとき（例 `flat-anime-pastel` の頭の上の輪）は `--no-style` で引き継がない。除外に足す語は `--negative`。
- マスクの範囲は `--ellipse`・`--rect`（左,上,幅,高さ。繰り返し可）。画面の2割を超えると注意を表示する。手で作る場合は `scripts/pixai_mask.py`、要求を一から組み立てる場合は `pixai_compose.py --i2i <画像> --mask <マスク> --strength 0.75`（元画像の寸法で要求を作り、違う寸法のマスクを止める）。
- `--add` は直したい物を主語付きで書く（例 `both girls have cat ears`、`girl wearing a red beret`）。
- マスクは、描き足す物と、それが入る空き（耳なら頭の上の背景）を含め、描き直したくない形は外す。**マスクを大きくすると、範囲内の顔・表情・リボン・小物も描き変わる**（大きいマスクでも描き足しの成功率は上がらない）。顔にかけない。
- 主語を省くと、`cat ears` 等の語と結びついて「ベレー帽をかぶった小さな猫」のように別の物が描かれることがある。
- 物の差し替え（カップ→リンゴ）・消去（手を組ませる）は小さいマスクで安定する。描き足し（帽子・耳）は4枚中2枚程度なので4枚から選ぶ。
- **結果は、描き直した範囲を元の解像度で元画像と並べて確認する**（縮小表示では小さな描き足しの有無を見誤りやすい）。
- インペイント・i2i の項目（`mediaId`・`maskMediaId`・`strength`）は公式文書にないため、送信に `--allow-unverified` が必要。予告なく使えなくなる可能性がある。
- 確認結果は [PixAI APIの接続手順](pixai-api.md#inpaint-results)。

<a id="layout-control"></a>

### 構図を写す（ControlNet）・左右の描き分け（latentCouple）

どちらも v1 の公式文書にない項目で、SDXLのモデル（`haruka2` 等）で使う（Tsubaki.2 等は ControlNet 非対応で、latentCouple も効かない）。確認結果は [PixAI APIの接続手順](pixai-api.md#unverified-results)。

- **ControlNet**：ラフや既存の絵の構図を写す。普通の絵からは `canny`（線・形。最も強く写る）と `depth`（奥行き・向き）が効く。`openpose` は普通の絵では効かず（骨格画像は未確認）、`scribble` は failed になる。`pixai_compose.py --model haruka2 --controlnet canny:input/rough/p01-04.png[:重み]`。
- **latentCouple**：画面を長方形に分けて、左右の人物の髪・服を描き分ける。指定どおりに描き分けられるが、**3人目が増えることがある**。使う場合は要求JSONを手で書き（下の例）、4枚から人数の合うものを選ぶ。人数の問題が解けるまで、２人のコマの標準は `--layout` とインペイントによる修正にする。

```json
{"api": "v1", "parameters": {"prompts": "2girls, side by side, park AND girl, long red hair, green dress AND girl, short blue hair, yellow raincoat",
  "modelId": "1861558740588989558", "width": 1280, "height": 848, "batchSize": 4,
  "latentCouple": {"type": "rect", "divisions": ["1:1", "1:2", "1:2"], "positions": ["0:0", "0:0", "0:1"], "weights": [0.2, 0.8, 0.8]}}}
```

<a id="compose"></a>

### 引数から要求JSONを組み立てる（`scripts/pixai_compose.py`）

**PixAI APIで生成する要求の標準の組み立て手段。** モデル・絵柄・背景・人物・LoRA・画風プリセット・生成設定を引数で受け取り、要求JSONを `input/pixai/requests/<ID>.json` へ保存する。通信はせず、保存後に `pixai_batch.py generate` と同じ送信なし確認を表示する。`--execute` と費用確認フラグを渡したときだけ送信へ引き継ぐ。保存した要求JSONは手で編集してよい。

```powershell
python -X utf8 scripts/pixai_compose.py --id p01-03 --seed 123 `
  --char1-appearance "<見た目>" --char1-action "<ポーズ・行動>" `
  --scene "upper body, from below" --background "school rooftop, blue sky" --style "<絵柄>" `
  --style-preset moe-pastel --mode standard --lora '${PIXAI_LORA_MIO}:0.8'
# ２人のコマ：姿勢と位置関係を --layout で外見より前に置く
python -X utf8 scripts/pixai_compose.py --id p01-05 --layout "girl on the right, boy on the left, facing each other" `
  --char1-appearance "<見た目>" --char2-type boy --char2-appearance "<見た目>" --scene "upper body"
# ControlNet・参照画像（v1・公式文書にない機能。SDXLのモデルで使う）
python -X utf8 scripts/pixai_compose.py --id p01-04 --model haruka2 --char1-appearance "<見た目>" `
  --reference output/pixai/candidates/chara-mio/r002.png --controlnet canny:input/rough/p01-04.png --adetailer
```

- **モデル**：`--model tsubaki2`（既定。`.env.pixai` の `PIXAI_MODEL` で変えられる）・`tsubaki3`・`haruka2`・`hoshino2` 等の `config/pixai-models.json` の名前、または `--model-version-id` と `--model-type dit|sdxl`。`--list-models` で一覧。mode・画風プリセットに非対応のモデル（SDXL・初代Tsubaki系）に `--mode`・`--style-preset` を付けるとエラーにする（公式：Tsubaki.2・Tsubaki.3 系以外では mode が拒否され、style は無視される）。mode を省略すると一覧の `default_mode` を使い、ないモデルでは送らない。
- **順序**：「人数タグ（人物から自動。１人なら `solo`、人物なしは `no humans`）→ `--layout`（複数人物の姿勢と位置関係）→ 人物（２人以上なら `girl`・`boy` を各人物の先頭に置く）→ `--scene` → `--background` → `--style` → 品質タグ」。入力の文は書き換えずに連結する。
- **品質タグ**：既定は `masterpiece, best quality`（公式の例文の語。効果の比較は未検証）。入力に同じタグがあれば付けない。`--quality-tags`・`--no-quality-tags`・`PIXAI_QUALITY_TAGS` で変える。
- **除外**：`PIXAI_NEGATIVE_PROMPT`（`--negative-base`。どちらもなければ `text, speech bubble, panel border, watermark`。空文字で付けない）→ `--negative`。v1 では公式文書にない項目になるため、既定の除外は付けず、`--negative-base`・`--negative` を指定したときだけ送る。
- **LoRA**：`--lora ID[:重み[:トリガー語]]` を繰り返す（v2は最大5件、v1は最大3件）。IDは数字か `${PIXAI_LORA_…}`。v1 にはトリガー語の項目がないため、トリガー語はプロンプトへ足す。
- **v1 になる引数**：`--upscale`・`--adetailer`（公式）、`--i2i`（＋`--strength`・`--mask`）・`--controlnet 種類:画像[:重み]`・`--reference 画像`（公式文書にない項目。[確認結果](pixai-api.md#unverified-results)）。生成済みのコマを直すときは `pixai_edit.py` を使う。v1 は `width`・`height`（512〜1280）で寸法を決めるため、`--size 1.5k` と 1:3・3:1 は使えない。v1 の除外（`negativePrompts`）・seed は公式文書にない項目になる（受理と seed の効果は確認済み）。
- **.env.pixai で上書きできる設定**：読むのは `PIXAI_MODEL`・`PIXAI_QUALITY_TAGS`・`PIXAI_NEGATIVE_PROMPT`・`PIXAI_PROMPT_HELPER`・`PIXAI_CHECK_IDENTITY` の5つだけで、APIキーの行は読まない。優先順は 引数 ＞ 環境変数・`.env.pixai` ＞ 既定。
- **絵柄・背景・人物の文**：`.env.pixai` の `PIXAI_STYLE_`・`PIXAI_BACKGROUND_`・`PIXAI_CHAR_` の値をそのまま引数へ渡す。このスクリプトは変数を読まず、`${変数名}` は（`--lora` を除き）エラーにする。
- 識別特徴の点検を使う場合だけ、`--cast-from 既存の要求ID` で登場人物の登録を写す。

<a id="character-variables"></a>

### キャラクター・絵柄・背景・LoRAを .env.pixai から読み込む（依頼があった場合）

人間が見た目を一括で変えて再生成できるように、プロンプトとLoRAのIDを作品ルートの `.env.pixai` の変数にし、要求JSONからは `${PIXAI_CHAR_MIO}`・`${PIXAI_STYLE_MAIN}`・`${PIXAI_BACKGROUND_CLASSROOM}`・`${PIXAI_LORA_MIO}` のように参照できる。**人間から依頼があった場合だけ**行う。APIキー・URLは共通設定の `.env` に置き、`.env.pixai` には書かない。

1. 変数名の案（`PIXAI_CHAR_`・`PIXAI_STYLE_`・`PIXAI_BACKGROUND_`・`PIXAI_LORA_` ＋半角英大文字・数字・`_`）と値を示し、ユーザーに確認する。`PIXAI_LORA_` の値はLoRAのバージョンID（数字）だけ。
2. `python -X utf8 scripts/pixai_batch.py env-set PIXAI_CHAR_MIO --value-file input/pixai/prompts/mio.txt` で `.env.pixai` へ書く。他の行は変更しない。
3. `templatize PIXAI_CHAR_MIO --dry-run` で置き換える箇所を確認し、`templatize PIXAI_CHAR_MIO` で要求JSON内の同じ文を変数に置き換える（v1 の `lora` のキーも対象）。
4. `vars` で変数名を確認し、変数名と使う要求を [PixAI一括生成の記録](../production/PIXAI-BATCH.md) に残す。

以後、人間は `.env.pixai` の値を書き換えてから `generate` を再実施できる。生成時には変数を展開した要求が実行記録に残る。許可した４種類の接頭辞以外の変数・APIキーは要求へ展開しない。同じ変数が環境変数と `.env.pixai` の両方にあると止まる。実際の編集例は [利用者向けREADME](../pixai-prompts/README.md)。

### 作画後の照合（組版の前に必ず行う）

全コマの採用画像が揃ったら、組版へ進む前に作品の [ネーム点検表](../reviews/NAME-REVIEW.md) の「作画後の照合表」を、コマごとに**画像を実際に開いて**記入する。「計画」は字コンテの主対象・動作・画角・人物、「画像で見えたもの」は画像に実際に描かれた内容を書く。不一致は再生成・配置の変更・計画の見直しのどれかで解消し、採否と理由を残す。記入が終わるまで組版へ進まない。実行記録の `mediaSafetyLevel` が `nsfw` の画像は、掲載先の基準に照らして採否を判断する（値がないことは安全を意味しない）。

### 組版

フキダシ・縦書きセリフ・画中の文字・コマ枠は、同梱の `scripts/typeset_manga.py` で組版する（使い方は [読みやすさ](japanese-manga-readability.md#typeset-script)）。会話のフキダシにはしっぽを付け、話者の口元へ向ける。顔・手・重要な小物の範囲に文字を置かない。画中の物に書かれた文字は、物そのものを描いた差し込みとして見せる。依頼にない作品名・ページ番号・ロゴ・署名をページへ入れない。

オノマトペは `templates/onomatopoeia/catalog.json` を意味・読み・用途・強さで検索し、`placement_hint_ja` と [反復して使う語の配置](../../templates/onomatopoeia/README.md#反復して使う語の配置) を確認する。色が必要なら `scripts/recolor_onomatopoeia.py` で色版を作る（テンプレートへ戻さない）。

見た目が採用可能で一部分だけ違うとき（耳・小物・手の向き等）は、**PixAIのインペイントを第一候補にする**（[インペイント](#inpaint)）。構図・表情・ほかの人物を保ったまま、コマの作り直しと同じ費用で直せる。インペイントで直らない場合は imagegen の局所修正かコマの作り直しを検討する。原画と編集版を両方保持する。

### PNGプレビューの確認

`pixai_batch.py build` でページPNGを作ったら、WebUIのプレビュータブ、または各ページの最新版（`output/build/page-NN/vNNN/` の数字が最大のフォルダ）の `page-NN-display.png` をページ順に提示する。ページ送りのHTMLを作る場合は、外部ライブラリ・外部通信を使わず、既存のPNGを相対パスで参照し、`output/build/preview.html` に置く。右から左へ読む作品では ← を次のページにする。**ブラウザーは起動しない**。実在を確認した絶対パスを提示し、ユーザーが自分で開く。

## 費用の確認

PixAIの生成はクレジットを使う（会員プランの付与分・購入分）。**残高・消費量を照会するAPIは公式文書にない**ため、スクリプトは無料を判定しない。

1. 生成の範囲（タスク数・1タスクの枚数・モデル・mode・解像度・LoRA・Hires・ADetailer・参照画像）を利用者に示す。
2. 利用者が**その範囲のクレジット消費を明示的に許可した場合だけ** `--confirm-credits` を付け、`--cost-note` に確認した残高・許可範囲・日時を書く。キーの設定、接続確認や生成の依頼だけでは有料利用の許可とみなさない。
3. 範囲を超える場合（ページの追加、mode・解像度・枚数の変更、公式文書にない機能）は改めて許可を得る。
4. 実消費は自動測定しない（記録の `actualCreditCost` は `null`）。必要なら利用者がPixAIの画面で確かめ、制作記録に残す。

ページの最終寸法は掲載・印刷目的から別途決める。1回の生成サイズへページ全体を押し込む必要はない。

## 原画を保持するPSD

PNGを先に確認し、修正なしの回答とPSD作成指示がそろってからPSDを作る（[PSDの引き渡し](psd-handoff.md)）。`pixai_batch.py build --write-psd` は `scripts/export_composed_psd.py` で、未加工原画を非表示グループに丸ごと格納し、配置用の全体画像を別レイヤーにして、コマ外だけをピクセルマスクで隠す。原画・配置行列・マスクを残して再配置できる方式で、スマートオブジェクトではない。CSPでの実読込確認は別途必要。

## 出典・確認範囲

仕様の出典・確認日は [PixAI APIの接続手順](pixai-api.md#出典確認範囲)（2026-10-25）。プロンプトの書き方・場面の展開・照合の手順は、このキットの漫画制作の運用をPixAI（人物別入力のない１本のプロンプト）に合わせた制作提案で、PixAIでの効果は未検証。
