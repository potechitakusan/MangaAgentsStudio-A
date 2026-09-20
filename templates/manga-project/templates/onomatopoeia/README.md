# 汎用オノマトペ素材

NovelAIに限らず、漫画・イラスト等の組版へ使えるモノクロ透過素材。38語形×3書体＝114枚。`index.html` を開くと、ネット接続なしで意味・読み・用途・強さ・書体・反復数から探せる。

書体は `block`（baan-v2基準）、`burst`（doon-v1基準）、`drybrush`（gogogo-v1基準）。外見を文章で指定して生成したため、同一フォントファイルのような厳密な字形統一ではない。小書き・縁・傾きに差があり、ハァの小書きはやや大きい。反復ゴ・ド・ザ・ガは承認済みの1文字素材連結で4〜7文字を別IDにしている。

画像は `catalog.json` の相対パスで参照。実alphaのあるグレースケール、原則高さ256px以下、可逆WebP。軽量化前の高解像度原画を同梱するものではない。大きく拡大すると細部が不足する場合は別生成等で対応し、見た目を確認する。

モノクロ利用は元素材をそのまま使う。色版はプロジェクトルートで次のように作り、テンプレートへ追加しない。PythonとPillowが必要。

```powershell
python scripts/recolor_onomatopoeia.py --input templates/onomatopoeia/images/block-baan.webp --output output/onomatopoeia-colored/block-baan.png --ink-color '#C02030' --white-color '#FFF2D6'
```

黒側・白側を別指定し、灰色は元の濃淡で混合する。alphaは不変。白を透明にする処理ではない。複雑な形の変更は画像編集で行う。WebPを受け付けないアプリ向けには `python scripts/export_onomatopoeia_png.py block-baan` でPNGへ変換できる。

[利用条件はCC0 1.0](LICENSE.md)。指定画像と自作メタデータは商用・改変・再配布可、クレジット不要。第三者の権利・ツール・コーパスには適用しない。条件付き頻度調査の上位語を含むが、全漫画の普遍的な上位20語を保証しない。
