---
name: manga-external-panel-i2i
description: QwenやNovelAI等で下絵・撮影・参照画像を条件に漫画のコマ原画を作り、修正・切り抜き・ページ組立へ進めるときに使う。接続確認だけ、文字だけの生成、imagegenによる新規のコマ・ページ作画には適用しない。
---

# 画像を条件に外部機能でコマ原画を作る

このSkillは作品一式へ同梱する。以下のパスは作品ルート基準。生成方式の選択は `manga-ai-production`、共通の判断手順は `docs/knowledge/external-panel-i2i.md` が担う。

## 適用と資料

画像を条件に１コマずつ作画する方針が決まったら、共通文書と採用したモデル・版の資料だけを読む。初期画像の変形、複数画像の参照、制御画像、外見・画風の専用参照を区別し、利用できる入力と費用を実行環境で確かめる。

- Qwen-Image 2.1の記録を使う場合：`docs/knowledge/image-generation/qwen-image-2.1.md`。別版や別ノードの動作保証にはしない。
- NovelAIの場合：`docs/knowledge/novelai-api.md` と `docs/knowledge/novelai-composed-production.md`。接続・費用・再送はこのサービスの手順に従い、t2i成功をi2i検証済みにしない。
- その他の場合：対象モデルの対応入力・現行仕様を確認する。既存モデルの画像順・強度・APIフィールドを転用しない。

Blender、特定レンズ、LoRA、imagegenの用途制限を全作品の既定にしない。作品で採用した制限と今回の許可範囲を引き継ぐ。画像生成・編集に使うSkillとツールが提供されていることを確認して、その手順に従う。

## 制作の進め方

1. 注目対象、画角、見える人数、顔の見せ方、動作の前後、残す接点を字コンテから受け取る。演出の不足は `manga-cinema-review` や `manga-immersion-review` の担当資料へ戻す。
2. コマ割りとページ寸法は既存の `docs/knowledge/panel-layout-policy.md` と `docs/knowledge/page-layout.md` に従う。構図・外見・小物の役割を分けて入力を用意し、実際の接続・添付と実送信文を対応させる。
3. 代表的な難所で入力方式と保持条件を試し、採用できる条件で残りへ展開する。不一致に応じて資料、指示、モデル固有設定、局所編集、切り抜きを選び直す。再試行は今回の回数・費用の範囲内に限る。
4. 採用画像を実際に開き、生成実寸と切り抜き範囲を確認する。仕上げモデルやLoRAを使った場合も、左右・衣装・表情・道具・隠した顔と前後の連続性を照合する。
5. ページに組み立て、`docs/knowledge/japanese-manga-readability.md` と `docs/knowledge/manga/08-workflow-review.md` の確認へ戻る。PNGの修正確認後、指示のあるPSDだけを `docs/knowledge/psd-handoff.md` に従って作成する。

通常の制作記録には実入力、設定、採用原画、修正理由、切り抜き、後処理、失敗と未確認事項を残す。記録項目と比較の扱いは共通文書C6を使う。フィードバックや個人の必須工程への登録は、それぞれユーザーの依頼がある場合だけ行う。
