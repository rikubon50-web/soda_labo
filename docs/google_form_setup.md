# Googleフォーム設定手順 — リードマグネット受け取りフォーム

**所要時間**: 約20分  
**必要なもの**: Googleアカウント（rikubon50@gmail.com）

---

## Step 1: フォームを作成する（5分）

1. [forms.google.com](https://forms.google.com) を開く
2. 「新しいフォームを作成」→ 空白
3. タイトルを入力:
   ```
   【無料テンプレ受け取り】AIで1人メディアを動かすチーム設計テンプレート
   ```
4. 説明文を入力:
   ```
   AIメディア「SODA」が実際に使っているAgent設計テンプレートを無料でお届けします。
   メールアドレスをご入力ください。
   ```

5. 質問を2つ設定する:

   **質問1（必須）**
   - 種類: 「短文回答」
   - 質問文: `メールアドレス`
   - 必須: ON
   - 入力の検証: メールアドレス形式

   **質問2（任意）**
   - 種類: 「短文回答」
   - 質問文: `AIを使って何をやってみたいですか？（任意）`
   - 必須: OFF

6. 右上の「送信」ボタン → 「リンク」タブ → URLをコピーして保存

---

## Step 2: Google Driveにテンプレをアップロードする（5分）

1. [drive.google.com](https://drive.google.com) を開く
2. 「マイドライブ」→「新規」→「ファイルのアップロード」
3. `/Users/rikubon50/Desktop/SODA/products/lead_magnet_ai_team_template.md` をアップロード
   （または PDF に変換してからアップロードする）
4. アップロードしたファイルを右クリック→「共有」→「リンクを知っている全員」に変更
5. 「リンクをコピー」して保存

---

## Step 3: 自動返信メールを設定する（10分）

フォームに回答があった瞬間に、テンプレのダウンロードリンクを自動送信する。

1. フォームを開いた状態で、右上の「︙（縦3点）」→「スクリプトエディタ」
2. 以下のコードを貼り付ける（`DRIVE_URL` と `YOUR_NAME` を書き換える）:

```javascript
function onFormSubmit(e) {
  const DRIVE_URL = "【Step2でコピーしたGoogle DriveのURL】";
  const YOUR_ACCOUNT = "@【あなたのXアカウント名】";
  const NOTE_URL = "note.com/【あなたのnoteアカウント名】";

  const email = e.namedValues["メールアドレス"][0];
  if (!email) return;

  const subject = "【SODA】AIチーム設計テンプレートをお届けします";
  const body = `
ご登録ありがとうございます！

AIメディア「SODA」です。
お約束した「AIで1人メディアを動かすチーム設計テンプレート」をお届けします。

━━━━━━━━━━━━━━━━━━
▼ テンプレートのダウンロード
${DRIVE_URL}
━━━━━━━━━━━━━━━━━━

テンプレートの内容:
・5つのAgent役割定義（CEO / Planner / Writer / Editor / Secretary）
・全体フローと指示書テンプレート
・よくある失敗パターン3つと解決策

---

毎日の実験記録をXとnoteで公開しています。
続きはこちらで読めます:

X: ${YOUR_ACCOUNT}
note: ${NOTE_URL}

何かあればXのDMでお気軽に。

SODA
  `.trim();

  GmailApp.sendEmail(email, subject, body);
}
```

3. 「保存」（Ctrl+S）
4. 左メニュー「トリガー」→「トリガーを追加」
   - 実行する関数: `onFormSubmit`
   - イベントのソース: `フォームから`
   - イベントの種類: `フォーム送信時`
5. 「保存」→ Googleアカウントの権限を許可

---

## Step 4: テスト送信する（2分）

1. フォームのプレビューを開く（目のアイコン）
2. 自分のメールアドレスで回答を送信
3. メールが届くか確認
4. ダウンロードリンクが開けるか確認

---

## Step 5: URLを記録して各所に設置する

フォームのURL（短縮推奨）を以下に設置する:

| 設置場所 | 対応ファイル |
|----------|-------------|
| Xプロフィール | 手動で設定 |
| X固定ポスト | 手動で設定（docs/x_profile_copy.md を参照） |
| note記事末尾 | writer.md のCTAテンプレに含める |
| docs/funnel_status.md | 設定済みに更新 |

---

## フォームURL・DriveURLの記録欄

**Googleフォーム URL**:
```
https://forms.gle/wsBvmZph85SNRPN96
```

**Google Drive テンプレURL**:
```
https://drive.google.com/file/d/1Cku1xhCGzUwEAdfHmO4A6w6lniErZXa4/view?usp=sharing
```

**設定完了日**: 2026-04-20
