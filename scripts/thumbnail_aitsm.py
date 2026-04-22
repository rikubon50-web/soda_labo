#!/usr/bin/env python3
"""
AIそれって本当？シリーズ専用サムネイル生成モジュール。
Pillowで毎回同じレイアウト・同じ色・同じフォントを描画する。
"""

from __future__ import annotations
import re
from datetime import date
from pathlib import Path

SODA_DIR = Path(__file__).parent.parent

# ── キャンバス ──────────────────────────────────────────────────────
W, H = 1280, 720

# ── カラーパレット ──────────────────────────────────────────────────
BG_TOP     = (10, 10, 25)      # ダークネイビー
BG_BOTTOM  = (22, 8, 38)       # ダークパープル
ACCENT     = (200, 16, 46)     # シリーズカラー（深紅）
WHITE      = (255, 255, 255)
GRAY       = (155, 155, 175)
YELLOW     = (245, 198, 55)

# ── フォント ────────────────────────────────────────────────────────
_FONTS = {
    "bold":   "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
    "medium": "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "light":  "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "fallback": "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
}


def _font(weight: str, size: int):
    from PIL import ImageFont
    path = _FONTS.get(weight, _FONTS["fallback"])
    if Path(path).exists():
        return ImageFont.truetype(path, size)
    return ImageFont.truetype(_FONTS["fallback"], size)


def _gradient(draw, w: int, h: int) -> None:
    for y in range(h):
        t = y / h
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    """日本語を max_width に収まるよう1文字単位で折り返す"""
    lines, cur = [], ""
    for ch in text:
        test = cur + ch
        if draw.textlength(test, font=font) > max_width:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def generate(theme: str, verdict: str | None = None) -> Path:
    """
    サムネイルを生成して保存パスを返す。

    Args:
        theme:   本日の説（例: "筋トレすると自己肯定感が上がる説"）
        verdict: 判定テキスト（例: "条件付きで本当"）。Noneなら判定パネルなし。
    """
    from PIL import Image, ImageDraw

    img  = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # 背景グラデーション
    _gradient(draw, W, H)

    # ── ① シリーズバッジ ────────────────────────────────────────────
    f_badge = _font("medium", 38)
    badge   = "AIそれって本当？"
    bw      = int(draw.textlength(badge, font=f_badge))
    bx, by  = 80, 70
    draw.rectangle([bx - 18, by - 10, bx + bw + 18, by + 50], fill=ACCENT)
    draw.text((bx, by), badge, fill=WHITE, font=f_badge)

    # ── ② アクセントライン ──────────────────────────────────────────
    draw.rectangle([80, 168, W - 80, 172], fill=ACCENT)

    # ── ③「本日の説」ラベル ─────────────────────────────────────────
    f_label = _font("light", 28)
    draw.text((80, 190), "▶  本日の説", fill=GRAY, font=f_label)

    # ── ④ メインテーマ（折り返し対応）───────────────────────────────
    f_main  = _font("bold", 76)
    lines   = _wrap(draw, theme, f_main, W - 160)
    line_h  = 94
    total_h = len(lines) * line_h
    # 判定パネルがある場合は少し上にずらす
    y = (H - total_h) // 2 + (-35 if verdict else 10)
    for line in lines:
        lw = int(draw.textlength(line, font=f_main))
        draw.text(((W - lw) // 2, y), line, fill=WHITE, font=f_main)
        y += line_h

    # ── ⑤ 判定パネル（任意）────────────────────────────────────────
    if verdict:
        f_verdict = _font("medium", 32)
        v_text = f"本日の判定：{verdict}"
        vw = int(draw.textlength(v_text, font=f_verdict))
        vx = (W - vw) // 2
        vy = H - 108
        draw.rectangle([vx - 24, vy - 12, vx + vw + 24, vy + 48], outline=YELLOW, width=2)
        draw.text((vx, vy), v_text, fill=YELLOW, font=f_verdict)

    # ── ⑥ ウォーターマーク ─────────────────────────────────────────
    f_wm = _font("light", 22)
    draw.text((W - 172, H - 40), "SODA_LABO", fill=GRAY, font=f_wm)

    # ── 保存 ────────────────────────────────────────────────────────
    thumb_dir = SODA_DIR / "content" / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    today      = date.today().strftime("%Y-%m-%d")
    safe_theme = re.sub(r"[^\w\-]", "_", theme[:25])
    out_path   = thumb_dir / f"{today}_aitsm_{safe_theme}.png"
    img.save(out_path, "PNG")
    print(f"サムネイル生成完了（aitsm テンプレート）: {out_path}")
    return out_path


def extract_verdict(article_text: str) -> str | None:
    """note記事本文から判定テキストを抽出する"""
    m = re.search(r"本日の判定[：:]\s*(.+)", article_text)
    if m:
        return m.group(1).strip().lstrip("*").rstrip("*").strip()
    return None
