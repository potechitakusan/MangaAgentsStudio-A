# 漫画制作のノウハウ一覧

このテンプレートは、漫画の企画・字コンテ・ネーム・作画・PNG確認・PSD引き渡しを主軸に使う。まずPNGプレビューで確認・修正し、修正がなくなってから、指示のあるPSDを作成・検証して引き渡す。PSD作成の指示がなければ作るか聞いて回答を待ち、既に指示があれば再確認しない。原則、人間がCLIP STUDIO PAINTで仕上げて外部公開する。CBZは明示指定時だけ作成する。

説明は日本語。ファイル名、製品名、出典URL、機械用の識別子はそのまま記載する。脚本資料は必要箇所の補助参照に留め、原資料一式を読むことや映画の字コンテを作ることを前提にしない。

この一覧は作品への配布用。配布元内では、知識の本文は `docs/knowledge/` の原本を参照する。新規作品の作成時に本文も同梱され、以下のリンクから開ける。

## 使う場面から選ぶ

| 困っていること・工程 | 読むノウハウ | 記入・確認先 |
| --- | --- | --- |
| 漫画の作り方、紙面の基本を確認したい | [ネーム・紙面・作画の基礎](knowledge/manga/00-manga-basics.md) | [作品の狙い](story/BRIEF.md) |
| 物語とキャラを決めたい | [物語・人物・テーマ](knowledge/manga/05-story-character.md) | [場面設計](story/SCENE-TEMPLATE.md) |
| 描く瞬間をコマへ分けたい | [字コンテからネームへ](knowledge/manga/01-conversion.md) | [漫画の字コンテ](story/TEXT-STORYBOARD.md) |
| コマ割りを決めて単調さを防ぎたい | [コマ割り運用方針](knowledge/panel-layout-policy.md) | [コマ割り方針](production/PANEL-LAYOUT-POLICY.md) |
| 構図・反応・小物を選びたい | [主対象・画角・視点](knowledge/manga/02-visual-direction.md) | [場面設計](story/SCENE-TEMPLATE.md) |
| 無言・テンポ・めくりを調整したい | [変化・緩急・提示順](knowledge/manga/03-beat-pacing-timing.md) | [情報と反復の管理表](story/INFORMATION-SHEET.md) |
| 会話を絵で見せたい | [場面・台詞・小道具](knowledge/manga/04-scene-dialogue-props.md) | [漫画の字コンテ](story/TEXT-STORYBOARD.md) |
| 連載、群像、ギャグを作りたい | [連載とギャグ](knowledge/manga/06-series-comedy.md) | [情報と反復の管理表](story/INFORMATION-SHEET.md) |
| 演出の選択肢と比較例を見たい | [効果別の演出パターン](knowledge/manga/07-case-patterns.md)、[コマ配分の比較手順](knowledge/manga/09-worked-example.md) | [ネーム点検表](reviews/NAME-REVIEW.md) |
| 通読して改稿したい | [ネームからPSDまで](knowledge/manga/08-workflow-review.md)、[レビュー運用](knowledge/review-workflow.md) | [ネーム点検表](reviews/NAME-REVIEW.md) |
| 縦書き・フキダシ・読み順を直したい | [日本語漫画の読みやすさ](knowledge/japanese-manga-readability.md) | [確定セリフ](production/DIALOGUE.md) |
| AIで絵を作り、キャラを保ちたい | [画像制作と実験](knowledge/ai-production.md) | [実験記録](experiments/TEMPLATE.md) |
| 人間が仕上げられるPSDにしたい | [PSD引き渡しの条件](knowledge/psd-handoff.md) | [引き継ぎ仕様と検証](production/PSD-HANDOFF.md) |
| 用語や出典、採否を確認したい | [用語辞書](knowledge/glossary.md)、[新規取り込みの出典](knowledge/manga-sources.md)、[還元手順](knowledge/feedback-workflow.md) | [作品用語](story/TERMS.md)、[フィードバック](feedback/TEMPLATE.md) |

## 取り込んだ技法76項目

提供された日本語整理の技法を以下の6分野に収録した。各文書で参照元の要約、漫画への応用、独自例、未検証の効果を区別する。番号は検索用で、読む順や必須項目数を指定するものではない。

### 01 漫画の字コンテからコマとネームへ

| 番号 | ノウハウ |
| --- | --- |
| C01 | [字コンテを「読者が体験する順番」で書く](knowledge/manga/01-conversion.md#c01) |
| C02 | [漫画のコマ候補を作る。既存カットは必要時だけ対応させる](knowledge/manga/01-conversion.md#c02) |
| C03 | [カットと変化の単位とコマを別々に数える](knowledge/manga/01-conversion.md#c03) |
| C04 | [長いカットは「意味が変わる瞬間」で分割する](knowledge/manga/01-conversion.md#c04) |
| C05 | [統合は「同時に見ても意味が保たれるか」で決める](knowledge/manga/01-conversion.md#c05) |
| C06 | [字コンテの演出指定は「目的＋見える内容」にする](knowledge/manga/01-conversion.md#c06) |
| C07 | [沈黙を画面のある指示にする](knowledge/manga/01-conversion.md#c07) |
| C08 | [音・動き・内面を漫画の情報へ変換する](knowledge/manga/01-conversion.md#c08) |
| C09 | [「カメラ指示を避ける」の適用範囲を分ける](knowledge/manga/01-conversion.md#c09) |
| C10 | [ページ上で初めてわかる問題を確認する](knowledge/manga/01-conversion.md#c10) |

### 02 注目対象・画角・アングル・視点

| 番号 | ノウハウ |
| --- | --- |
| V01 | [画面の主体を一言で言えるようにする](knowledge/manga/02-visual-direction.md#v01) |
| V02 | [引きで状況、寄りで判断材料を渡す](knowledge/manga/02-visual-direction.md#v02) |
| V03 | [必要な情報からアングルを選ぶ](knowledge/manga/02-visual-direction.md#v03) |
| V04 | [見る人→対象→反応で認識を描く](knowledge/manga/02-visual-direction.md#v04) |
| V05 | [話し手より聞き手を描く](knowledge/manga/02-visual-direction.md#v05) |
| V06 | [切り返しは発言順より関係の変化で選ぶ](knowledge/manga/02-visual-direction.md#v06) |
| V07 | [背中・歩き方・手の接触で人物を見せる](knowledge/manga/02-visual-direction.md#v07) |
| V08 | [遮蔽物を情報の制限に使う](knowledge/manga/02-visual-direction.md#v08) |
| V09 | [客観と主観を切り替えて体験を作る](knowledge/manga/02-visual-direction.md#v09) |
| V10 | [空景を独立した意味のある画面にする](knowledge/manga/02-visual-direction.md#v10) |
| V11 | [同じ構図を反復し、差分を読ませる](knowledge/manga/02-visual-direction.md#v11) |
| V12 | [前後の絵の組み合わせで意味を作る](knowledge/manga/02-visual-direction.md#v12) |
| V13 | [空間の連続性を字コンテに残す](knowledge/manga/02-visual-direction.md#v13) |
| V14 | [重要なものが重要に見えるかを縮小して確認する](knowledge/manga/02-visual-direction.md#v14) |

### 03 変化の単位・緩急・提示のタイミングと間

| 番号 | ノウハウ |
| --- | --- |
| R01 | [変化の単位・構成の節目・短い間を区別する](knowledge/manga/03-beat-pacing-timing.md#r01) |
| R02 | [緩急と提示のタイミングを別々に設計する](knowledge/manga/03-beat-pacing-timing.md#r02) |
| R03 | [出来事・描写・読了の三つの時間を分ける](knowledge/manga/03-beat-pacing-timing.md#r03) |
| R04 | [変化を動詞で書き、反復を見つける](knowledge/manga/03-beat-pacing-timing.md#r04) |
| R05 | [刺激→認識→選択→応答を見える形にする](knowledge/manga/03-beat-pacing-timing.md#r05) |
| R06 | [転換の前は予期、後は吸収の間を作る](knowledge/manga/03-beat-pacing-timing.md#r06) |
| R07 | [延ばすほど、期待か危険を変化させる](knowledge/manga/03-beat-pacing-timing.md#r07) |
| R08 | [反応の順番で場面の重心を作る](knowledge/manga/03-beat-pacing-timing.md#r08) |
| R09 | [場面の長短と密度を組み合わせる](knowledge/manga/03-beat-pacing-timing.md#r09) |
| R10 | [遅く入り、必要な余韻を残して出る](knowledge/manga/03-beat-pacing-timing.md#r10) |
| R11 | [読者の知識を三通りに配置する](knowledge/manga/03-beat-pacing-timing.md#r11) |
| R12 | [核心語と核心の絵を、反応が始まる位置へ置く](knowledge/manga/03-beat-pacing-timing.md#r12) |
| R13 | [ページめくりを情報の境界に使う](knowledge/manga/03-beat-pacing-timing.md#r13) |
| R14 | [間を測るときは「読者の状態」を記録する](knowledge/manga/03-beat-pacing-timing.md#r14) |

### 04 場面・台詞・小道具

| 番号 | ノウハウ |
| --- | --- |
| D01 | [場面の始まりと終わりの差を書く](knowledge/manga/04-scene-dialogue-props.md#d01) |
| D02 | [各人物の「欲しいもの」と「やり方」を分ける](knowledge/manga/04-scene-dialogue-props.md#d02) |
| D03 | [台詞に相手を動かす動詞を付ける](knowledge/manga/04-scene-dialogue-props.md#d03) |
| D04 | [言葉・隠した本音・本人も言えない欲求を分ける](knowledge/manga/04-scene-dialogue-props.md#d04) |
| D05 | [説明を人物が使う情報に変える](knowledge/manga/04-scene-dialogue-props.md#d05) |
| D06 | [長台詞を反応で区切る](knowledge/manga/04-scene-dialogue-props.md#d06) |
| D07 | [第三の物事に本当の争点を預ける](knowledge/manga/04-scene-dialogue-props.md#d07) |
| D08 | [台詞と行動を反対方向へ向ける](knowledge/manga/04-scene-dialogue-props.md#d08) |
| D09 | [短い返事や言い淀みに仕事を与える](knowledge/manga/04-scene-dialogue-props.md#d09) |
| D10 | [人物ごとの言葉と身振りを決める](knowledge/manga/04-scene-dialogue-props.md#d10) |
| D11 | [日常動作を感情と結び付ける](knowledge/manga/04-scene-dialogue-props.md#d11) |
| D12 | [小道具に複数の役目を持たせる](knowledge/manga/04-scene-dialogue-props.md#d12) |
| D13 | [場所に行動を生ませる](knowledge/manga/04-scene-dialogue-props.md#d13) |
| D14 | [人の出入り・音・中断で場面を曲げる](knowledge/manga/04-scene-dialogue-props.md#d14) |

### 05 物語・人物・テーマ

| 番号 | ノウハウ |
| --- | --- |
| S01 | [一文で主役・目的・抵抗・代償を言う](knowledge/manga/05-story-character.md#s01) |
| S02 | [テーマを選択と結果で示す](knowledge/manga/05-story-character.md#s02) |
| S03 | [欲しいものと、それを妨げる信念を決める](knowledge/manga/05-story-character.md#s03) |
| S04 | [人物資料を行動の差にする](knowledge/manga/05-story-character.md#s04) |
| S05 | [圧力のある選択で人物の本質を見せる](knowledge/manga/05-story-character.md#s05) |
| S06 | [対抗する側にも筋の通った目的を持たせる](knowledge/manga/05-story-character.md#s06) |
| S07 | [変化の途中を飛ばさない](knowledge/manga/05-story-character.md#s07) |
| S08 | [前の行動が次の難題を生むようにする](knowledge/manga/05-story-character.md#s08) |
| S09 | [冒頭は動く状況と見る理由を渡す](knowledge/manga/05-story-character.md#s09) |
| S10 | [伏線は初回にも自然な役目を与える](knowledge/manga/05-story-character.md#s10) |
| S11 | [クライマックスを一つの行為や絵へ集める](knowledge/manga/05-story-character.md#s11) |
| S12 | [構成法を作品の読み味に合わせる](knowledge/manga/05-story-character.md#s12) |

### 06 連載・群像・ギャグ

| 番号 | ノウハウ |
| --- | --- |
| L01 | [毎話なにをする漫画かを動詞で書く](knowledge/manga/06-series-comedy.md#l01) |
| L02 | [話の解決と継続する葛藤を分ける](knowledge/manga/06-series-comedy.md#l02) |
| L03 | [長所が問題も生む人物網を作る](knowledge/manga/06-series-comedy.md#l03) |
| L04 | [主線と副線を別に成立させてから編む](knowledge/manga/06-series-comedy.md#l04) |
| L05 | [切り替えを時間の省略と対比に使う](knowledge/manga/06-series-comedy.md#l05) |
| L06 | [引きに複数の型を持つ](knowledge/manga/06-series-comedy.md#l06) |
| L07 | [群像では反応と利害を分ける](knowledge/manga/06-series-comedy.md#l07) |
| L08 | [ギャグを設定と人物から生ませる](knowledge/manga/06-series-comedy.md#l08) |
| L09 | [フリ→展開→オチの順に読ませる](knowledge/manga/06-series-comedy.md#l09) |
| L10 | [笑いが弱いときはフリへ戻る](knowledge/manga/06-series-comedy.md#l10) |
| L11 | [繰り返しギャグは意味を更新する](knowledge/manga/06-series-comedy.md#l11) |
| L12 | [笑わせ方と重い場面の位置を人物に合わせる](knowledge/manga/06-series-comedy.md#l12) |

## 必要な場合だけ使う補助知識

- [映画的演出と没入](knowledge/immersion-and-cinema.md)：画角や連続動作の参照が必要な場合。
- [物語構造の調査](knowledge/story-structure.md)：構成理論や出典を詳しく確認する場合。
- [動画試作の運用](knowledge/video-previsualization.md)、[動画プロンプト](knowledge/video-prompting.md)、[動画ツール](knowledge/video-tools.md)、[動画の連結と編集](knowledge/video-assembly.md)：動画を試す明示依頼がある場合。
- [Codexの運用](knowledge/codex-operation.md)：スキルと継続記録を管理する場合。

本文の原本は配布元の共通知識、記入用雛形とこの一覧は作品テンプレートで管理する。作品作成スクリプトが組み合わせて配布するため、作成後の作品は参照元フォルダがなくても利用できる。
