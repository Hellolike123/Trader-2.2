from trader_shared.fusion_core import merge_decisions


class TestFusionAccuracy:
    def _chan_buy(self):
        return {"chanlun": {"buy_points": [{"type": "一类买", "price": 28.5, "confidence": 3}]}}

    def _chan_sell(self):
        return {"chanlun": {"sell_points": [{"type": "一类卖", "price": 32.0, "confidence": 3}]}}

    def _momentum_bullish(self):
        return {"momentum": {"score": 75, "direction": "bullish", "signals": ["MACD金叉", "均线多头"]}}

    def _momentum_bearish(self):
        return {"momentum": {"score": 25, "direction": "bearish", "signals": ["MACD死叉", "均线空头"]}}

    def _momentum_neutral(self):
        return {"momentum": {"score": 50, "direction": "neutral", "signals": []}}

    def _wyckoff_bullish(self):
        return {"wyckoff": {"spring": True, "phase": "accumulation"}}

    def _wyckoff_bearish(self):
        return {"wyckoff": {"upthrust": True, "phase": "distribution"}}

    def test_all_bullish(self):
        result = merge_decisions(
            self._chan_buy(), self._momentum_bullish(), self._wyckoff_bullish(),
            regime="正常", current_price=30.0, bars=[],
        )
        assert result["weighted_score"] > 0, f"Expected positive score for all bullish, got {result['weighted_score']}"
        assert result["weighted_score"] > 0.3, (
            f"Expected high positive score for all bullish, got {result['weighted_score']}"
        )

    def test_all_bearish(self):
        result = merge_decisions(
            self._chan_sell(), self._momentum_bearish(), self._wyckoff_bearish(),
            regime="正常", current_price=30.0, bars=[],
        )
        assert result["weighted_score"] < 0, f"Expected negative score for all bearish, got {result['weighted_score']}"

    def test_conflicting_signals(self):
        result = merge_decisions(
            self._chan_buy(), self._momentum_bearish(), self._wyckoff_bullish(),
            regime="正常", current_price=30.0, bars=[],
        )
        assert "disagreement" in result, f"Missing disagreement in result: {result.keys()}"

    def test_all_neutral(self):
        neutrals = {"chanlun": {"divergence": {"bottom_divergence": False, "top_divergence": False}}}
        result = merge_decisions(
            neutrals, self._momentum_neutral(),
            {"wyckoff": {}}, regime="正常", current_price=30.0, bars=[],
        )
        assert abs(result["weighted_score"]) < 0.1, (
            f"Expected near-zero score for all neutral, got {result['weighted_score']}"
        )
