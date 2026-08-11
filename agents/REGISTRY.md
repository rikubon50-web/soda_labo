# Agent & Skill Registry

新しいAgentやSkillを追加したら、このファイルに必ず追記する。
CEO・Secretaryはここを参照して、何が使えるかを把握する。

---

## Agents（役割を持つ担当）

| エージェント名 | ファイル | 役割概要 |
|---|---|---|
| CEO | agents/ceo.md | 方針決定・企画採否・公開判断 |
| Secretary | agents/secretary.md | タスク管理・進行整理・ログ記録 |
| Planner | agents/planner.md | 企画案量産・タイトル・切り口提案 |
| Writer | agents/writer.md | 記事・動画台本の下書き |
| Editor | agents/editor.md | 品質向上・トーン統一・冗長削除 |
| Researcher | agents/researcher.md | 採用テーマの一次取材・取材ノート作成 |
| Critic | agents/critic.md | note記事の敵対的批評・AI臭採点 |

| Analyst | agents/analyst.md | noteメトリクス分析・勝ちパターン抽出・次週テーマ提案 |
| Growth | agents/growth.md | CTA最適化・導線設計・無料→購買の接続管理 |

### 追加候補（未作成）
- Product Claude：マネタイズ設計・デジタルプロダクト企画

---

## Skills（再利用可能なタスクモジュール）

| スキル名 | ファイル | 使用シーン |
|---|---|---|
| ニュース解説 | agents/skills/skill_news_explainer.md | AI・ビジネスニュースを噛み砕く記事 |
| フック作成 | agents/skills/skill_hook_writing.md | 記事・動画の冒頭を強化する |

---

## 追加ルール

### 新Agentを追加するとき
1. `agents/_template_agent.md` をコピーして新ファイルを作成
2. 役割・責任範囲・出力形式を記入
3. このREGISTRYに追記
4. Secretary.mdの「タスク分解」に必要なら追記

### 新Skillを追加するとき
1. `agents/skills/_template_skill.md` をコピーして新ファイルを作成
2. いつ使うか・何を入力するか・何を出力するかを記入
3. このREGISTRYに追記

### 削除・統合するとき
- ファイルを削除する前にREGISTRYから先に外す
- 統合する場合は旧ファイルにリダイレクト1行を残す
