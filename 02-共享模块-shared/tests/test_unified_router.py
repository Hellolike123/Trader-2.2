from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Add shared paths
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

from run_trader import format_live_wechat_card


class TestUnifiedRouter(unittest.TestCase):
    def test_format_live_wechat_card_avoids_markdown_headings(self):
        """确保微信端友好卡片没有 Markdown 标题 (#) 和加粗 (**)"""
        mock_report = {
            "name": "南网科技",
            "symbol": "688248.SH",
            "current": 59.33,
            "change_pct": 2.70,
            "state_label": "防守观察",
            "base_status": "防守观察",
            "theory_status": "防守观察",
            "low_zone": "57.50-58.64元",
            "stop": 56.11,
            "confirm": 59.84,
            "position_cap": 10,
            "volume_text": "早盘放量，午后缩量震荡。",
            "chanlun": {
                "trend_label": "筑底震荡",
                "buy_point_text": "二类买"
            },
            "wyckoff": {
                "wyckoff_text": "Spring 确认摆脱震荡"
            },
            "fusion": {
                "weighted_score": 0.85,
                "confidence": 75
            },
            "fib_retrace": {
                "golden_bid": 57.50
            }
        }
        
        card = format_live_wechat_card(mock_report)
        
        # 验证没有 # 标题
        self.assertNotIn("#", card)
        # 验证没有 ** 粗体
        self.assertNotIn("**", card)
        # 验证包含黄金挂单
        self.assertIn("黄金挂单", card)
        self.assertIn("57.50元", card)
        # 验证四维诊断大白话
        self.assertIn("缠论结构", card)
        self.assertIn("二类买", card)
        self.assertIn("威科夫量价", card)
        self.assertIn("主筹码峰", card)
        self.assertIn("动能大单", card)
        self.assertIn("决策置信度", card)


if __name__ == "__main__":
    unittest.main()
