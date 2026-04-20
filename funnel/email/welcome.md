# ウェルカムメール

フォーム登録直後に自動送信されるメール。

## 現在の設定

- 送信方法: Google Apps Script（onFormSubmit）
- スクリプト: docs/google_form_setup.md 参照
- 状態: ✅ 稼働中

## メール本文

```
件名: 【SODA】AIチーム設計テンプレートをお届けします

ご登録ありがとうございます！

AIメディア「SODA」です。
お約束した「AIで1人メディアを動かすチーム設計テンプレート」をお届けします。

━━━━━━━━━━━━━━━━━━
▼ テンプレートのダウンロード
https://drive.google.com/file/d/1Cku1xhCGzUwEAdfHmO4A6w6lniErZXa4/view?usp=sharing
━━━━━━━━━━━━━━━━━━

テンプレートの内容:
・5つのAgent役割定義（CEO / Planner / Writer / Editor / Secretary）
・全体フローと指示書テンプレート
・よくある失敗パターン3つと解決策

---

毎日の実験記録をXとnoteで公開しています。
X: @SODA_LABO
note: note.com/soda_labo

何かあればXのDMでお気軽に。

SODA
```

---

## ステップメール

| ステップ | タイミング | ファイル |
|---------|-----------|---------|
| Step 1 | 登録直後 | welcome.md（このファイル） |
| Step 2 | 3日後 | step2_day3.md |
| Step 3 | 7日後 | step3_day7.md |
