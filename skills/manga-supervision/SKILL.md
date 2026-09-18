---
name: manga-supervision
description: 漫画の場面で狙う笑い・魅力・感情・関係・展開の効果を監修する。字コンテ・ネームの表現相談とPNGレビューで、場面に必要なテーマの知識を選び、人物や設定を保つ改善案を比較するときに使う。
---

# 漫画の監修

版0.3.2では既存のギャグと、下表の追加15テーマの試行版を扱う。メインエージェントが制作判断と採否を統合し、別エージェントの起動を必須にしない。

## 対象と参照先

対象の場面・版、字コンテ相談か画像レビューか、中心にする効果、保ちたい人物像・感情・設定・制作条件を確認する。既存の企画から分かることは読み取り、不足が提案を左右するときだけ確認する。

作品ルートを基準に `docs/knowledge/supervision/routing.md` を読み、選んだテーマの本文だけを使う。

| 必要な監修 | 参照先 |
| --- | --- |
| 笑いの前提・ずれ・証拠 | `docs/knowledge/supervision/gag/README.md` |
| 指摘する・黙る・受け流す等の反応 | `docs/knowledge/supervision/tsukkomi/README.md` |
| 所作・視線・距離から相手を意識する瞬間 | `docs/knowledge/supervision/allure/README.md` |
| 実力・判断・覚悟と格の違い | `docs/knowledge/supervision/stature/README.md` |
| 異変への予感・脅威・恐怖 | `docs/knowledge/supervision/horror/README.md` |
| 怒りの争点・口論・決裂 | `docs/knowledge/supervision/conflict/README.md` |
| 不在・悲しみ・喪失後の余韻 | `docs/knowledge/supervision/grief/README.md` |
| 好意の主体・照れ・関係の一歩 | `docs/knowledge/supervision/romance/README.md` |
| 任せる範囲・親密さ・信頼 | `docs/knowledge/supervision/trust/README.md` |
| 受け取りの差・気まずさ・すれ違い | `docs/knowledge/supervision/awkwardness/README.md` |
| 失うもの・残る機会・切迫した選択 | `docs/knowledge/supervision/urgency/README.md` |
| 解釈の更新・発覚・種明かし | `docs/knowledge/supervision/revelation/README.md` |
| 局面の変化・逆転・解放 | `docs/knowledge/supervision/payoff/README.md` |
| 人物固有の可愛げ・愛着 | `docs/knowledge/supervision/endearment/README.md` |
| 目的・情報・一手への応答 | `docs/knowledge/supervision/bargaining/README.md` |
| 謝罪・選ぶ距離・和解・救い | `docs/knowledge/supervision/reconciliation/README.md` |

共通の因果・人物・読順・終幕は `docs/knowledge/review-workflow.md` の「共通知識の参照先」へ戻す。出典の主張と応用の範囲を確かめる場合は `docs/knowledge/supervision/sources.md` を使う。

専用知識のない効果は既存の制作知識とレビューで扱う。試行版の効果を実証済みと説明しない。既存の人物の声と作品の表現範囲を保つ。

## 字コンテ・ネームへの提案

1. 主効果と人物の目的を確認し、選んだ項目の適用条件に照らして現在の案を見る。その効果を担う人物・手掛かり・前後の変化を確かめる。同じ視線や沈黙だけで効果を決めず、全テーマを総当たりで適用しない。
2. 人物の欲求・知識・行動と既出の事実を保つ。ツッコミの短さ・強さ、接近・露出を一律に増減する修正にしない。色気の監修でヌード・性行為を加えず、好意や関係の成立を勝手に補わない。
3. 必要な案だけを返す。各案に変更箇所、読者に渡す手掛かり、期待する効果、失う可能性のある効果を添える。
4. 併用時は主効果を優先する。修正が真剣な感情、関係の選択、設定上の条件を取り消していないかを見る。強調のために人物の能力・知識・責任を変更せず、好意の成立、赦し、関係の再開、回復を一つの反応から自動で補わない。問題がなければ変更しない案を返す。

## プレビューへの提案

1. 対象PNGなどを実際に開き、版・ページ・該当箇所を確認する。画像が未確認なら字コンテ上の見立てに限定する。
2. 見えた事実、読みの仮説、改善案を分ける。読者が笑った、色気や恐怖を感じた、悲しんだ等の未計測反応を事実にしない。
3. 意図が伝わらない原因に対応する修正を示す。局所の台詞・証拠・反応で直るか、前提からの変更が必要かを区別する。
4. 改善案と守るべき効果を返し、メインの採用後は該当箇所を再提示・再確認する。

## 返す内容

- 対象・段階・実際に確認した範囲。
- 主効果、確認に使ったキット内の文書・項目。
- 観察／読みの仮説／変更案／期待する効果と代償。
- 競合点・未確認事項と、メインが判断する採否。

必要なら作品内の `docs/reviews/SUPERVISION.md` を使う。既存のレビュー重みや評価項目を追加しない。通常の制作から依頼のない知識還元を行わない。
