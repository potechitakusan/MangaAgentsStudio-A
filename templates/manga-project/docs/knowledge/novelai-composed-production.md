# NovelAI素材生成＋Codex組版の標準手順

ユーザー採用：2026-09-20。NovelAIで漫画制作を始めるときに読む。生成条件は時間とモデルで変わるため送信直前に再確認する。

## 制作開始と画風

1. 作品のOPTION、既存の画風指定、`config/novelai-production-policy.json` を確認する。作品固有の指示を優先する。
2. 画風が未指定なら3番の見本案内へ進み、ユーザーの画風ID選択を待つ。既に指定されている場合は再選択を求めない。指定済みでも画風・見本の案内を求められた場合は3番に従う。
3. 見本はキットの `resources/novelai-style-samples/index.html`。`project.json` の `sourceKitRelativePath` を作品ルート基準で解決し、`config/novelai-style-presets.json` の `kit_sample_library_relative_path` を結合する。ファイルの実在だけを確認し、その絶対パスだけを案内する。画風案内ではHTML本文・画像を開いたり読み込んだりせず、候補の列挙・特徴説明・要約・比較提案・画像添付を行わない。記録のない既存作品では、会話等で既知のキット設置先を使ってよい。設置先が不明、移動済み、または見本が存在しない場合は未確認と伝えて場所を確認し、絶対パスを推測しない。見本画像は作品へコピーしない。
4. ユーザーの選択前はNovelAI API等による生成試作を行わず、0 Anlasの場合も含めて待つ。待機対象は画風の確定と画風に依存する作画であり、別途依頼されたあらすじ整理などは進めてよい。選択回答を受けて `config/novelai-style-presets.json` の該当IDと照合し、作品の採用IDとプロンプトを記録する。`default_ids` は選択可能なIDの一覧であり、候補説明・全画風の混合・先頭候補の無断自動選択を指示するものではない。特定作家・漫画家の名前は使わない。`sample_prompt_prefix` は見本用の人物数指定であり、実作品で全コマを女性2人に固定する規則ではない。
5. 採用した画風文・除外文・人物外見文・主要生成設定を共通化し、コマごとに動作・画角・背景だけを変える。seedだけで一貫性は保証しない。指定場面に見える人物だけのキャラクタープロンプトを送る。

現在の10画風は掲載順の `style-01`〜`style-10`（2026-09-21更新）。同日のユーザー指示で「細く鋭い線のお絵描き」を除外し、直前の `style-10`（かわいいカラー漫画）を `style-09`、`style-11`（かわいいモノクロ漫画）を `style-10` へ詰めた。見本HTML・カタログ・新規作品の設定は同じIDを使う。既存作品の旧IDを新IDとして読み替えず、必要な場合は画風名とプロンプトを照合する。

## 素材生成と組版

文字だけのt2iと、初期画像・参照画像を使う方式を区別する。画像条件付きのコマ作画を選んだ場合だけ `manga-external-panel-i2i` と [共通手順](external-panel-i2i.md) を併用し、入力の実装・追加費用は [API手順](novelai-api.md) で確認する。画風選択・費用確認・文字と枠の分離はt2iにも適用する。Qwenの画像順や強度をNovelAIへ流用しない。

Codexでコマ割りと読み順を設計し、NovelAIは文字・枠のない組版用イラストに使う。全身や周囲の余白を残しやすい構図で生成し、配置時に回転・拡大・部分表示する。必要な場面では人物だけを枠より前へ置く。見せたい接点・顔・手と、文字を置く余地を生成前に決める。

### 本番前の人物試作

コマの生成へ進む前に、主要人物ごとに人物試作を１回生成する（Opusの無料条件内。複数人物を１枚にまとめてもよい）。字コンテやキャラ設定の外見（髪の長さ・色、眼鏡、上着と制服の重ね順、小物の左右）と照合し、ずれがあれば人物の外見文を直してから本番へ進む。試作と修正内容は制作記録へ残す。依頼で人物試作を省く指示がある場合はそれに従う。

### 生成寸法と配置

コマ別の素材は**コマより広い範囲**を生成し、ページではコマ枠（コマ外を白で覆う最上段の枠レイヤー）とマスクで必要な部分だけを見せる。元画像は全体をPSDのレイヤーに残し、人間があとからペイントソフトで位置・大きさを調整できるようにする。

- 寸法は要求JSONの `width`・`height` に書く。ページ全体の生成希望寸法（`generationCanvas`）と違ってよい。縦横比はコマの形に近いものを選ぶと、使える範囲が広くなる（横長のコマは横長、縦長のコマは縦長）。寸法の例は `config/novelai-production-policy.json` の `panel_canvas_examples`。Opusの無消費候補の画素数・steps等の条件は従来どおり確認する。
- コマ内の見せ方はページ構成JSONの `focus`（画像内でコマの中心に置く点）・`zoom`・`rotation` で指定する。
- 「引き・上から中庭を見下ろす」のように空間を見せるコマで、大きく拡大して一部だけを見せると空間が消える。引きの構図そのものを生成し直す。
- 配置の後にも、字コンテの主対象・動作・人物・小物がコマ内に見えるかを、下の照合表で確かめる。顔がコマ端で半分切れる等の問題は配置を直す。

<a id="prompt-writing"></a>

### 要求プロンプトの組み立て

字コンテのコマを、画像に**見える形**の語へ置き換えてから書く。2026-09-29の比較で、プロンプトが原因の不一致（人のいない靴だけ、紙が折られたまま、座るはずが立っている）が出た書き方を避けるための制作提案であり、効果は検証中。

1. **順番**：人数と主対象（`1boy, solo` / `no humans`）→ 見える姿勢・動作・表情 → 画角・被写体の大きさ・画面内の位置 → 場所の目印 → 時間・光 → 画風。画風の定型文は最後に置き、コマ固有の内容を先に書く。
2. **否定語を肯定側に書かない**：`not smiling`、`no people`、`without glasses`、`neither …` は、その語（smiling、people、glasses）に反応して逆に出ることがある。避けたい要素は `negative_prompt` に書く。人物なしは `no humans` のタグを使う。
3. **意図ではなく見える形を書く**：`about to sigh`、`as if starting to reply`、`awkward` ではなく、`eyes half closed, shoulders dropped, mouth slightly open, looking aside` のように顔・手・体の形で書く。
4. **途中ではなく状態を書く**：`unfolding a paper airplane` は途中の形（折られたまま）で出やすい。見せたいのが結果なら `an unfolded sheet of paper with fold creases, held open in both hands` のように、その瞬間に見える状態を書く。
5. **部分のアップは誰の体かを書く**：`dark school shoes` だけでは靴が置いてある絵になる。`1boy, lower body, standing, legs in navy trousers and white lab coat hem, school shoes, a paper airplane on the ground at his feet` のように、人物・体の範囲・姿勢を書く。手のアップも `1girl, hands only, …` のように持ち主を書く。
6. **2人のコマ**：１つの文に２人分の外見を続けて詰めると、姿勢の指定が埋もれ、外見も混ざりやすい。まず１人ずつのコマに分けられないかを検討する（相手は画面外・肩越しなど）。２人を同時に描く場合は、姿勢と位置関係（`sitting side by side on the floor, knees up, girl on the right`）を外見より前に書き、外見は識別に必要な最小限にする。人物ごとに分けて書く機能（`v4_prompt` の `char_captions`）を使う場合は、使う前に公式スキーマで書式を確認する。
7. **画角は字コンテから選ぶ**：`from above`・`from below`・`from behind` は候補であり、全コマの先頭に付ける決まりではない。何を見せるかに合わせて選び、画面内の目印（`rooftop edge at the top of the frame`、`courtyard far below`）や被写体の大きさ（`small in frame`、`upper body`）も書く。同じ画角が続く場合は意図を確認する。

8. **識別の特徴を要求ごとに書く**：人物が出る要求には、その人物を見分ける特徴（髪の色と長さ、眼鏡の形、服の重ね順・内側の服、小物）を毎回同じ語で書く。前のコマに書いたから省く、ということをしない。2026-09-29の検証では、要求ごとに書き方が揺れたコマで髪色・眼鏡の形・内側の服がばらついた。特徴は人物試作で採用した見本に合わせて `input/novelai/characters.json` に登録し、要求ごとの登場人物と、そのコマで見える特徴を `cast` に書く。

```json
{
  "characters": {
    "mio": {"name_ja": "日向ミオ", "features": {
      "hair": "light brown short bob hair", "hairpin": "yellow hairpin on left bangs",
      "outer": "open yellow hoodie worn over navy blazer"}},
    "ren": {"name_ja": "月島レン", "features": {
      "hair": "short black hair", "glasses": "thin black rectangular glasses",
      "outer": "white lab coat over navy blazer"}}
  },
  "cast": {
    "p01-01": {"mio": "all"},
    "p01-03": {"mio": ["outer"]},
    "p04-05": {"mio": "all", "ren": "all"}
  }
}
```

`"all"` は全特徴、配列はそのコマで見える特徴だけ（手元のアップなら服の袖だけ等）。特徴の文字列は要求のプロンプトにそのまま含める（大文字・小文字は区別しない）。キャラ別プロンプトを `.env` の変数にしている場合は、展開後の文で点検する。

9. **数値の年齢や man・woman を入れない**：`25 years old`、`40歳` のような数値の年齢は見た目に効きにくい。`man`・`woman` を書くと、`1girl`・`1boy` で指定した人物とは別の２人目が現れることがある（2026-09-29のユーザー指示）。人物は `1girl`・`1boy`・`solo` と外見の語で書く。`teenage`、`high school student`、`adult` のような年代・立場の語は使ってよい。大人びて・幼く見せる調整は、体格・顔立ち・服装の語も合わせて行う。

10. **人物・物の関係を名称と別に確かめる**：人物と物を並べただけでは、持つ・触れる・入れる等の関係が消えることがある。そのコマを別の行為と区別する条件を、画像で判定できる1～3項目にしてから、該当する項目だけを書く。英語例を全コマへ足す決まりではない。

| 観点 | 書く内容の例 |
| --- | --- |
| 接点・所持 | 手で持つ（`water bottle in her hand`）、顔に当てる、手の形（`cupped hands`、`palms pressed together`） |
| 操作 | 結ぶ・直す・留める手、左右の手が別々の端を担当する |
| 内外・上下・距離 | 袋の中へ入れる、地面のすぐ近く（`close to the ground`）、台の上 |
| 視線の相手 | 互いを見る（`smiling at each other`）、紙面へ目を下げる |
| 画角と方向 | 背面から見る登校、移動先との位置 |

短くするときは、本文・人物別本文・座標・否定文をまとめて読み、同じ意味が他に残っているかを確かめる。別々に削って問題がなかった２か所を、同時に削っても安全とは推測しない。根拠はV5 Fullの通常t2iでの観察（[制作根拠E4](image-generation/production-evidence.md#e4)、[NovelAI V5のN1](image-generation/novelai-v5.md#n1)）で、他の版・画像入力での効果は未確認。

`novelai_batch.py generate` は送信前に上の2・3・5・6・8・9と画角の連続を点検し、警告を表示する。警告が残る要求は、プロンプトを直すか、残す理由を [NovelAI一括生成の記録](../production/NOVELAI-BATCH.md) に書いてから `--accept-warnings` を付けて送信する。点検は語の検出であり、プロンプトの良否を判定するものではない。

<a id="batch"></a>

### 要求JSON・一括生成・採用・組み直し（人間が再実施できる形）

NovelAIの生成は結果のばらつきが大きい。人間がページ単位・全ページで何度か生成し直し、採用する画像を選んでから続きを進められるように、要求と構成をすべてファイルに残し、同梱の `scripts/novelai_batch.py` で生成・採用・組み直しを行う。独自の生成・組版スクリプトで置き換えない。

| 置き場所 | 内容 |
| --- | --- |
| `input/novelai/requests/p01-03.json` | １コマ１要求のJSON（`novelai_api.py` と同じ形式）。ファイル名は `p{ページ2桁}-{コマ2桁}`、差し替え案は `p01-03b.json` のように末尾を足す。人物試作は `chara-mio.json` 等 |
| `output/novelai/candidates/p01-03/r001.png` | 生成候補。実行ごとに番号が増え、上書きしない。隣に実行記録 `.novelai.json` |
| `input/novelai/adopted.json` | 採用した候補（`adopt` で記録） |
| `input/typeset/page-01.json` | 組版指定（フキダシ・文字・画中の文字・文字を置かない範囲）。形式は [組版スクリプト](japanese-manga-readability.md#typeset-script) |
| `input/pages/page-01.json` | ページ構成：`layout.json`、組版指定、コマごとの採用画像（`request` またはファイル直接の `source`）と `focus`・`zoom`・`rotation`、効果音等の `overlays` |
| `output/build/page-01/v001/` | 組み直しの結果。版ごとに新しいフォルダ。`page-01.png`、指定時は `page-01.psd`、`build.json`、組版の点検結果 |

ページ構成の例：

```json
{
  "schema_version": 1,
  "layout": "output/layout/page-001-v1/layout.json",
  "typeset": "input/typeset/page-01.json",
  "panels": [
    {"panel": 1, "request": "p01-01", "focus": [0.5, 0.4]},
    {"panel": 2, "request": "p01-02", "focus": [0.5, 0.5], "zoom": 1.1},
    {"panel": 3, "source": "output/fixed/p01-03-fix.png", "original_source": "output/novelai/candidates/p01-03/r002.png"}
  ],
  "overlays": [{"name": "効果音 パタ", "source": "templates/onomatopoeia/images/burst-pata.webp", "center": [700, 1300], "scale": 0.6, "rotation": -10}]
}
```

コマンド（作品ルートで実行）：

```powershell
# 送信せずに内容・寸法・seedを確認
python -X utf8 scripts/novelai_batch.py generate --page 1
# 1ページ分を１枚ずつ順に生成（全ページは --all、特定コマは --ids p01-02,p01-04）
python -X utf8 scripts/novelai_batch.py generate --page 1 --execute --confirm-zero-anlas --confirm-v5-allowance --cost-note '確認した方法・日時'
# 候補を見比べて採用
python -X utf8 scripts/novelai_batch.py list --page 1
python -X utf8 scripts/novelai_batch.py adopt p01-02 --candidate 3
# 同じページ・コマ・配置で組み直す（PSDも作るときは --write-psd）
python -X utf8 scripts/novelai_batch.py build --page 1
python -X utf8 scripts/novelai_batch.py build --all --write-psd
```

- `generate` は初回は要求のseed、２回目以降は乱数のseedを使う（`--seed request` で固定）。１件ずつ送信し、送信間隔は既定３秒、１回の上限は既定30件。失敗したら残りを送らずに止まり、自動再送しない。結果不明の実行記録があるコマは、確認して記録を移すまで再生成しない。費用確認のフラグは `novelai_api.py` と同じ意味で、確認していないフラグを付けない。
- `build` は採用画像が未選択なら止まる。画像がコマの一部を覆えない配置は警告を出す。人間がコマンドで作ったPSDは、あとからペイントソフトで調整する前提とする。Codexが引き渡すPSDは、従来どおりPNGの修正確認とPSD作成の指示がそろってから作る。
- 要求の書き方を比べるときは、変更前の採用要求を差し替え案（`p01-03b.json` 等）と別に残す。両方の `parameters.seed` を同じ値にして `--seed request` で生成し、Seedの値を変えて複数の組を作る。変えた語以外の設定、未変更の要求（対照）が成功したか、失敗したSeedを含む全試行を記録する。対照が成功していない組から、その語が必要・不要とは結論しない。推奨の方法であり、全コマに必須の回数ではない。根拠は[制作根拠E4](image-generation/production-evidence.md#e4)。
- Codexは最初の作画でもこの手順を使い、各ページのコマンドを [NovelAI一括生成の記録](../production/NOVELAI-BATCH.md) に残す。ユーザーに見せるPNGは `build` の出力を使う。

<a id="character-variables"></a>

### キャラ別プロンプトを .env から読み込む（依頼があった場合）

人間が見た目を一括で変えて再生成できるように、キャラ別プロンプトを作品ルートの `.env` の変数にし、要求JSONからは `${NOVELAI_CHAR_MIO}` のように参照できる。**人間から依頼があった場合だけ**行う。

1. 変数名の案（`NOVELAI_CHAR_` ＋半角英大文字・数字・`_`。例：`NOVELAI_CHAR_MIO`）と、各変数に入れるプロンプトを示し、ユーザーに確認する。
2. `python -X utf8 scripts/novelai_batch.py env-set NOVELAI_CHAR_MIO --value-file input/novelai/char-mio.txt` で `.env` へ書く。`.env` の他の行（APIキー）は表示・変更しない。
3. `templatize NOVELAI_CHAR_MIO --dry-run` で置き換える箇所を確認し、`templatize NOVELAI_CHAR_MIO` で要求JSON内の同じ文を変数に置き換える。
4. `vars` で変数名を確認し、変数名と使う要求を [NovelAI一括生成の記録](../production/NOVELAI-BATCH.md) に残す。

以後、人間は `.env` の値を書き換えてから `generate` を再実施できる。生成時には変数を展開した要求が実行記録に残る。`NOVELAI_CHAR_` 以外の変数・APIキーは要求へ展開しない。同じ変数が `.env` と `.secrets/` の両方にあると止まる。

### 作画後の照合（組版の前に必ず行う）

全コマの採用画像が揃ったら、組版へ進む前に作品の [ネーム点検表](../reviews/NAME-REVIEW.md) の「作画後の照合表」を、コマごとに**画像を実際に開いて**記入する。「計画」は字コンテの主対象・動作・画角・人物、「画像で見えたもの」は画像に実際に描かれた内容を書く。計画を写しただけの記入や、未確認のままの「一致」は不可。不一致は再生成・配置の変更・計画の見直しのどれかで解消し、採否と理由を残す。記入が終わるまで組版へ進まない。

2026-09-29の比較では、照合を行わなかった側で、着地したはずの紙ひこうきがない、紙を開くはずが折られたまま、座るはずが立っている、等の不一致が６件残った。

### 組版

フキダシ・縦書きセリフ・画中の文字・コマ枠は、同梱の `scripts/typeset_manga.py` で組版する（使い方は [読みやすさ](japanese-manga-readability.md#typeset-script)）。独自に組版コードを書く場合も、次を満たす。

- 会話のフキダシにはしっぽを付け、話者の口元へ向ける。しっぽを付けない場合（画面外の声等）は理由を記録する。
- 顔・手・重要な小物の範囲に文字を置かない。範囲は画像を見て指定する。
- 調査票・手紙・画面など、画中の物に書かれた文字は、物そのものを描いた差し込み（アップのコマや、コマ内に置いた用紙の絵）として見せる。ゲームの会話枠のような四角を画面の上に重ねない。
- 依頼にない作品名・ページ番号・ロゴ・署名をページへ入れない。

通常は `from above`、`from below`、`from behind` から場面に適した一つを選ぶ。`dutch angle`、`cinematic angle` は補助として適度に使う。全タグを毎回同時に入れない。水平・横からの視点は、新人物と背景の紹介、静止による緊張など意図を記録した場合だけ使う。俯瞰・背面でも重要な表情や接点が消えていないか確認する。

この画角の優先は `config/novelai-production-policy.json` の採用設定に従うNovelAI制作の運用で、外部i2i全般の規則ではない。画角の意図は [画角・視点](manga/02-visual-direction.md) で判断し、生成・切り抜き後も接点・表情・動作のつながりを照合する。種類を増やすこと自体を目標にしない。

オノマトペは `templates/onomatopoeia/catalog.json` を意味・読み・用途・強さ・書体・反復数で検索する。素材の文字をそのまま完成形とせず、`placement_hint_ja` と [反復して使う語の配置](../../templates/onomatopoeia/README.md#反復して使う語の配置) を確認する。震えの「プル」は同じ素材を2個並べて「プルプル」にする。継続するざわめきは「ザワザワ」、賑わいは「ワイワイ」のように反復形を選ぶ。読む方向に沿って近接させ、PNGでひと続きの語として読めるか確認する。一瞬の「ドキ」等の単独で自然な用法や、既に連結済みの素材まで一律に2個にしない。この配置方針は2026-09-21のユーザー指示による。

適切な素材がなければ別の透過素材を生成し、実alpha・文字・反復数を確認する。反復の1文字連結は4〜7文字を別IDで扱う。セリフは原則縦書き・各列上詰めで組版し、枠・効果音・吹き出し・文字を分離する。オノマトペは音の出る時点のコマへ置く（着地音を滑空中のコマに付けない）。

見た目が採用可能で一部分だけ違うときにimagegenで局所修正する。原画と編集版を両方保持する。構図・人物数・動作全体の不一致は組版や生成条件を見直す。過去セッションの「再生成5枚まで」を新作品の恒久上限にはしない。各依頼の上限に従う。

## Opusの費用確認

原則1枚ずつ、通常サイズ相当の画素数と28以下のstepsを候補にする。採用済み見本の1344×704＝946,176画素・24stepsは候補範囲だが、この数値だけで無料と認定しない。モデル、契約、使用枠、入力画像や参照機能を含む実際のリクエストの費用を調べ、0 Anlasかつ残枠が確認できたときだけ無料枠として送信する。不明・有料なら止めて確認し、無断で有料へ移行しない。[契約条件](https://docs.novelai.net/en/subscription/)、[使用枠](https://docs.novelai.net/en/faq/)（2026-09-20確認）。

V5は回復する使用枠の制限がある。Opusだから無制限と説明しない。画像入力、拡大、アウトペインティングも別に費用を確認する。まず無料条件内で生成し、必要なら原画を保持した上で拡大または余白の追加描画を行う。拡大は元の細部が増える保証ではなく、追加描画は新しい内容と画風の確認が必要。

ページの最終寸法は掲載・印刷目的から別途決める。1回の生成サイズへページ全体を押し込む必要はない。1600×2400は既存比較の組版寸法であり必須値やOpus上限ではない。dpi・塗り足し等は別に確定する。

## オノマトペの色替え

テンプレートには透過モノクロ原本だけを置く。モノクロ時はそのまま使用。色が必要なら `scripts/recolor_onomatopoeia.py` で黒側・白側の色を指定し、元の濃淡で混ぜる。alphaは変更しない。色版は作品の `output/` 等へ保存し、テンプレートへ戻さない。複雑な描き直しだけimagegenを使う。NovelAI以外の透過モノクロ素材にも使える。

```powershell
python scripts/recolor_onomatopoeia.py --input templates/onomatopoeia/images/block-baan.webp --output output/onomatopoeia-colored/block-baan.png --ink-color '#C02030' --white-color '#FFF2D6'
```

## 原画を保持するPSD

PNGを先に確認し、修正なしの回答とPSD作成指示がそろってからPSDを作る。従来の引き渡し規則は省略しない。

`scripts/export_composed_psd.py` は未加工原画を非表示グループに丸ごと格納し、配置用の全体画像を別レイヤーにして、コマ外だけをピクセルマスクで隠す。imagegen修正前のNovelAI原画も指定できる。原画の画素を削除しない。配置レイヤーの回転・拡大はラスタライズされるため、スマートオブジェクトや可逆変形ではない。原画・配置行列・マスクを残して再配置できる方式。

既定はPNG＋記録JSONのみ。明示的な `--write-psd` でPSDを追加する。原画SHA-256、RGBA画素、マスク、日本語レイヤー名、再合成PNGを検証する。文字PNGは編集可能なテキストとは呼ばない。CSPでの実読込確認は別途必要。
