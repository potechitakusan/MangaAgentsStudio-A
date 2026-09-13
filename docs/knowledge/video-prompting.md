# 映画演出を試す動画制作とMiniMax H3プロンプト

確認日: 2026-09-12（JST）
適用範囲: ローカルComfyUIで短い映画風映像を作り、漫画の画角・動作・間・接続を検討する任意の補助機能。漫画制作の通常工程に動画生成を必須追加しない。
証拠区分: **確認事実**はリンク先の記載、**制作提案**は本プロジェクトの判断、**未検証**は実機・視聴評価が必要な事項を表す。

## モデルと参照方式を最初に決める

**確認事実:** 正式名は **MiniMax H3**。H3-Base-FL2VAはテキスト・始点画像・終点画像、H3-Base-Ref2VAは複数の画像・映像・音声参照に対応する。公式仕様は4〜15秒、24fps、32kHzステレオ音声。日本語は安定対応と記載された11言語に含まれる。H3-Context-IRはホスト型の前処理であり、公開重みのローカル実行だけでは公式サービスの全処理を再現しない。[MiniMax公式README](https://github.com/MiniMax-AI/MiniMax-H3)

**制作提案:** キャラ資料は人物の同一性、場面画像は構図・場所、開始画像は実際の先頭フレーム、と役割を区別する。人物資料を動画の先頭にそのまま表示したくない場合は、人物参照として扱うRef2VAか、その資料から先に作った場面画像をI2VAへ渡す。

**確認事実:** ComfyUIのFL2VA用とRef2VA用重みは別物。Ref2VAの参照タグは接続順に対応する。`match`は生成解像度に合わせて参照を縮小し、`max`はより大きい参照で同一性を狙う設定で、計算量も増える。[ComfyUIネイティブワークフロー](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native)

## 参照用プロンプトの組み立て

**確認事実:** H3の全参照モードは次の6節を使う。本文は英語、セリフ・歌詞・画面上の文字は原文を保つ。`<Subject N>`は再利用する人物などの内容、`<Picture N>`は具体的なフレームや構図の基準として区別する。[MiniMax全参照ガイド](https://raw.githubusercontent.com/MiniMax-AI/MiniMax-H3/main/skills/h3-prompt-writing/references/ref-en.txt)

| 節 | 書く内容 |
| --- | --- |
| `subject_definitions` | 参照の接続番号、人物・場所・画面構成など各参照の役割 |
| `summary` | 生成する短い場面と参照の使い方 |
| `retention_analysis` | 顔・衣装・背景など維持する要素と、意図して変更する要素 |
| `detailed_description` | 画面の初期状態から動作・反応・音までを再生順に記す |
| `overall_soundscape` | 環境音、足音、衣擦れなど |
| `non_diegetic_music` | 劇伴。不要なら `N/A` |

以下は形式説明用の**独自例・未検証**。画像1に人物、画像2に室内がある場合の例であり、実際の入力を見て置き換える。

```text
subject_definitions:
<Subject 1> is the adult negotiator in <Picture 1>, preserving his face, dark suit, white shirt, and narrow tie.
<Subject 2> is the room in <Picture 2>, preserving the table, doorway, and warm side lighting.

summary:
[reference generation] <Subject 1> calmly delivers one short line inside <Subject 2>.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and clothing.
<Subject 2> (appears in [Shot 1]): fully_preserved - layout and lighting.

detailed_description:
The video has a restrained live-action style.
[Shot 1] An eye-level medium shot places <Subject 1> beside the table in <Subject 2>. The camera remains still. He lifts his eyes toward the listener. His low, even voice (S1) says: <d>[Japanese] 話を聞いてください。</d> He pauses with relaxed shoulders.

overall_soundscape:
Quiet room ambience and a slight rustle of suit fabric.

non_diegetic_music:
N/A
```

**確認事実:** 始終フレーム系はこの6節とは異なり、画像と時刻の対応を先頭に置き、`integrated_multimodal_description`、`overall_soundscape`、`non_diegetic_music`を続ける。カメラは移動種類・必要な移動幅・速さを自然文で書く。話者ID `(S1)` 等を固定し、セリフを `<d>[Japanese] …</d>` に入れ、声質や演技はタグ外へ記す。複数ショットなら2番目以降に増加するカット時刻を指定する。[MiniMax始終フレーム系ガイド](https://raw.githubusercontent.com/MiniMax-AI/MiniMax-H3/main/skills/h3-prompt-writing/references/base-en.txt)

**制作提案:** 1生成1カットなら `[Shot 1]` だけでよい。時刻を増やして多数のカットを1回で生成する前に、個別カットの成立を確認する。曖昧な「強そう」「かっこよく」を、肩の脱力、視線、避ける方向、相手の転倒後の位置など観察可能な情報へ直す。カメラ固定と追跡移動など、同時に成立しない指示を混ぜない。

## 約20秒を4〜7秒のカットへ分ける

**確認事実:** ComfyUIでH3の長さは24fpsの `17k+5` フレーム単位に丸められる。解像度は32の倍数とし、標準的な横長キャンバスは1344×768。[ComfyUIプロンプトガイド](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-prompt-guide)

**制作提案:** 最初は各124フレーム・24fpsを4本とすると計算上約20.67秒。必要ならセリフや反応を切らない位置で約20秒に整える。フレーム数からの計算値と、実出力を検査した尺を両方記録する。

| 候補フレーム数 | 24fpsの計算尺 | 利用例（提案） |
| --- | --- | --- |
| 107 | 約4.46秒 | 短い反応、命令 |
| 124 | 約5.17秒 | 交渉、一連の回避と決着 |
| 141 | 約5.88秒 | 反応の間を含む動作 |
| 158 | 約6.58秒 | 開始と結果を明確に見せる動作 |

**制作提案:** 群衆全員が同時に攻撃する長い一文は、カットごとに「誰が先に動くか」「主役の動作」「相手の最終状態」へ分ける。攻撃側2名なら体格だけでなく髪型・シャツ色・立ち位置で区別し、接近→回避→相手が倒れる結果を読み取れる画角にする。人数を増やすのはこの連鎖が読めてから。

**制作提案:** 日本語は1カット1話者・短い1文から試す。戦闘中の会話を抑え、交渉カットと命令カットへセリフを置くと、意味と口の動きを確認しやすい。各カットで独立生成された声・環境音が接続時に変わる可能性があるため、音量、声質、頭切れ・末尾切れを実際に聞く。別TTSを使う場合も、口の動きが合うことを自動的に保証しない。

## キャラと空間の一貫性を保つ

**制作提案:** 参照画像と文で、顔、髪、衣装、左右の配置、照明方向を固定する。各カットの参照割当表を作り、別の人物を同じタグへ割り当てない。キャラ資料と生成用の場面画像は別に保存し、使用ファイル名・ハッシュを記録する。次カット用画像を作り直す際は同じ資料を参照し、前カットの最後の良いフレームも接続の基準にできる。

**制作提案:** 崩れた出力フレームを次の参照へ渡すと誤りを引き継ぐので、目、輪郭、袖、手足、衣装の一致を確認してから使う。修正はカット単位で行い、同時にプロンプト・解像度・モデル・ステップ数を変えない。単一seedの成功を一般化せず、少数の別seedでも成立するか必要に応じて比較する。

## 速度と品質を比較する

**確認事実:** Comfy-OrgはH3向けにpruned/量子化重みを再パッケージし、PyTorch cu130が使える場合は `int8_convrot` を優先している。`nvfp4_awq` テキストエンコーダーにはBlackwell必須との制限はない。[Comfy-Orgモデルカード](https://huggingface.co/Comfy-Org/MiniMax-H3)

**確認事実:** LarryvrhのTurbo LoRAは作者資料で4〜8stepを有効域とし、v4は高速で大きい動作を4stepで作ると残像が出る場合があると説明している。6〜8stepへの増加や旧v1との使い分けは作者の提案。これはMiniMax標準モデルの品質保証ではなく、学習中の派生モデルについての記載である。[Turbo作者モデルカード](https://huggingface.co/larryvrh/MiniMax-H3-Turbo-Lora)

**確認事実:** ModelTC/LightX2VのTurboは別系列。Ref2VA 4step v0.1は544p、FL2VAには768pの4/8step版があり、学習解像度・音声と映像のshift設定が異なる。名前が似ていても別系列LoRAやサンプラーを混ぜない。[ModelTC作者README](https://github.com/ModelTC/Minimax-H3-Turbo)

**確認事実:** FL2VA向け `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` は544p系の8-step v1.0で、標準LoRAローダー・Euler・映像shift12/音声shift3を使う。768p専用版の映像shift6と区別する。[作者のモデル表](https://github.com/ModelTC/Minimax-H3-Turbo/blob/main/README.md)、[設定手順](https://github.com/ModelTC/Minimax-H3-Turbo/blob/main/COMFYUI_SETUP_AND_INFERENCE.md)

**ローカル観察:** この8-step版を896×512/124framesで使用し、標準LoraLoaderModelOnly＋SigmaShift＋Eulerの経路で音声付き動画を生成できた。旧専用TurboLoRAノードへ新しい標準形式LoRAを入れる経路は採用していない。名称の「Turbo」だけで互換性を判断せず、対象ベース・キー形式・作者のworkflowを照合する。日本語2文は無誘導のASRで一致したが、ASRだけでは声質・口同期の合格とはしない。

**制作提案:** 動作確認済みの構成で基準を1本作り、遅い箇所がテキスト処理・重みロード・サンプリング・デコード・アップスケールのどこかを計測する。step短縮はロード時間を短縮しない。まず不要なアップスケールを外し、同一素材で4stepと8stepの可読性・顔・残像・日本語を比較する。量子化、pruned、Turboの有無、作者・版、実際の設定を記録し、公式サービスのデモ映像と同条件とは扱わない。

**確認事実:** ComfyUIはSage Attentionによる速度改善を案内しているが、対応dtype以外では標準attentionへ戻る場合がある。[ComfyUI速度改善資料](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)

**制作提案:** 既に対応するSage設定がある場合は利用状況をログで確認する。新たなバックエンド導入や大量の別モデル取得は、既存構成の実測と比較してから決める。

## 代替候補の扱い

以下は確認日現在の候補整理。**いずれも同一GPU・同一参照・同一場面でのH3比較は未検証**であり、「同等品質でもっと速い」と結論づけない。

| 候補 | 開発元・作者資料から確認した範囲 | 判断に残る条件 |
| --- | --- | --- |
| H3 + 現在あるTurbo | 既存参照資料を流用し、stepを比較できる | まず実測。新モデル取得が不要な場合の第一候補 |
| H3 + Larryvrh新版Turbo | 4〜8step、細部と高速動作のトレードオフを作者が記載 | 現在ある版との差、音声・複数人動作、VRAMを実測。単純な速さの向上とは限らない |
| H3 + ModelTC/LightX2V Turbo | 専用Ref2VA 4step版がある | 対応するサンプラー・shift・解像度、参照人物品質を検証 |
| LTX-2.5 distilled | 開発元は少stepの高速経路を提供。ComfyUIで同期音声映像生成を案内 | 別の22B重み、専用エンコーダー、VAE、upscalerが必要。H3との品質・実速度は未比較 |
| Wan2.2 TI2V-5B | 開発元は720p/24fps、公式コマンドは24GB以上のGPUを案内 | 16GB環境の動作・日本語音声の別工程・複数人同一性を検証 |

LTX-2.5の機能・構成は[Lightricks公式リポジトリ](https://github.com/Lightricks/LTX-2)と[公式ComfyUIガイド](https://docs.ltx.io/open-source-model/usage-guides/text-to-video)による。公式必要環境は32GB以上のVRAMを掲げるため、16GB環境へ無検証で置き換えない。[LTX必要環境](https://docs.ltx.io/open-source-model/getting-started/system-requirements) Wanの条件は[Wan2.2開発元README](https://github.com/Wan-Video/Wan2.2)による。

**制作提案:** 代替取得を依頼する場合は、モデルID、対象ファイル、配布元、保存先、必要容量、既存モデルを流用できる部分、見込む改善、未検証点を揃える。性能低下が小さい根拠が足りない段階では、取得を必須工程にしない。

## 評価記録

**制作提案:** 動画の完成判定を「MP4が出た」と「意図した場面に見える」に分ける。各カットについて次を記録する。

- 技術: 実尺、fps、縦横サイズ、音声トラック有無、生成時間、実ステップ数、モデルと参照、seed、エラー。
- 演出: 誰が何をしたか、動作の開始と結果、主役の余裕、相手の反応、画角が示す情報。
- 連続性: 顔・衣装、人数、左右・視線・進行方向、倒れた人物の状態、室内配置。
- 音声: 日本語の聞き取り、実際に話した語、話者、声質、口との一致、接続の音切れ。
- 漫画への還元: 採用したいコマ候補、必要な中割り、動画では成立しても静止画では補足が必要な情報。

技術検査、映像の目視、音声の聴取の実施状況を別々に残す。見ていない項目・聞いていない項目には「未確認」と記し、画像接触シートだけで動画の時間的一貫性を合格にしない。
