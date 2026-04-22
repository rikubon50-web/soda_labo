"""
ショー（企画）レジストリ。

新しい企画を追加するときの手順:
  1. scripts/shows/{show_id}.py を作成する
  2. REGISTRY に {show_id: "shows.{show_id}"} を追加する
  3. show モジュールに以下を実装する:
       SHOW_ID        : str          — 識別子（REGISTRY のキーと一致）
       SHOW_NAME      : str          — 表示名
       DAYS           : list[int]    — 実行曜日（0=月 〜 6=日）
       MEETING_INSTRUCTIONS : str   — 会議プロンプトに追加するセクション
       build_prompt(theme, date_str) -> str  — 生成プロンプト
       parse_meeting_decision(text) -> dict | None  — 会議ログからテーマ等を抽出
"""

import importlib
import sys
from pathlib import Path

# show_id → モジュールパスのマッピング
REGISTRY: dict[str, str] = {
    "aitsm": "shows.aitsm",
}


def get_show(show_id: str):
    """show_id に対応するショーモジュールを返す。"""
    if show_id not in REGISTRY:
        raise ValueError(
            f"未知のshow_id: '{show_id}'。"
            f"登録済み: {list(REGISTRY.keys())}"
        )
    scripts_dir = str(Path(__file__).parent.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    return importlib.import_module(REGISTRY[show_id])


def get_scheduled_shows(weekday: int) -> list[str]:
    """今日（weekday）に実行予定のショー ID リストを返す。"""
    result = []
    for show_id in REGISTRY:
        show = get_show(show_id)
        if weekday in getattr(show, "DAYS", []):
            result.append(show_id)
    return result
