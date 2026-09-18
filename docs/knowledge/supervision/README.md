# 漫画の監修知識

版0.3.1の監修は**ギャグのみ対応**する。字コンテ・ネームで笑いの表現案を考え、PNGプレビューで前提・ずれ・証拠・反応が伝わるかを確かめる。

- [ギャグのノウハウ](gag/README.md)：笑いの仕組み、期待と証拠、発想と点検。
- [監修を使う場面と進め方](routing.md)：必要な観点と主効果の選び方。
- [汎用知識](../review-workflow.md#common-knowledge)：人物・因果・情報・読順・終幕。

手順は `manga-supervision` にまとめ、メインエージェントが制作判断と採否を統合する。キットでは `skills/manga-supervision/SKILL.md`、作品では `.agents/skills/manga-supervision/SKILL.md` を使う。

他ジャンルを含む作品でも、笑いを狙う場面に限ってギャグ監修を使える。笑い以外の場面は既存の制作知識とレビューで扱う。

ギャグ監修文書の配布ファイル一覧は `distribution.json` に記載する。
