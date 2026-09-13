# Codexでの運用

確認日: 2026-09-12。

公式文書では、Skillsのnameとdescriptionを候補選択に使い、必要時に本文を読む。リポジトリのローカルSkillsは `.agents/skills/` に配置できる。[Build skills](https://learn.chatgpt.com/docs/build-skills)

AGENTS.mdはプロジェクトの指示を置く場所で、親子の適用範囲やoverrideがある。作品ルートから開始し、意図した指示が認識されているか確認する。[AGENTS.md公式文書](https://learn.chatgpt.com/docs/agent-configuration/agents-md)

スキル設計の参考資料として次の記事を参照した。具体的な発火条件、必要な資料だけを読む構成、常時指示の肥大化を避ける方針を、スキルの設計に採用する。[Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)

## このプロジェクトの選択

- 安定した約束はAGENTS.md、詳細な知識はdocs、特定場面の相談・レビュー手順はSkill、今回の制作目的は依頼文へ置く。
- Skillsは独立実行プロセスではない。メインエージェントが手順を使うか、利用可能なサブエージェントに対象と手順を渡す。
- 進捗ファイルは実行中の処理を保存する機能ではない。セッションが切れたら、記録した出力と実行IDを確認してから再開し、生成依頼を無条件で重複送信しない。
- 再開に必要な記録は現在の目的、完了ファイル、進行中処理、決定事項、未確定事項、直後の行動。外部サービスの秘密値は記載しない。
- モデル名や利用可能ツールをSkill内で固定しない。環境で使えるものを確認し、モデルの能力や価格を推測で書かない。

この文書は作品へ配布する。個別の指示原文と開発中の調査ログは配布しない。
