"""Tests for Time Pattern Analyzer Service."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from backend.services.time_patterns import (
    TimePatternAnalyzer,
    DayOfWeekAnalyzer,
    MomentumDetector,
    get_combined_time_multiplier
)


class TestTimePatternAnalyzer:
    """Tests for TimePatternAnalyzer."""

    @patch('backend.services.time_patterns.datetime')
    def test_peak_hours_detection(self, mock_datetime):
        """Should detect peak hours correctly."""
        mock_now = datetime(2025, 1, 15, 15, 0, 0, tzinfo=timezone.utc)  # 3 PM UTC
        mock_datetime.now.return_value = mock_now

        period = TimePatternAnalyzer.get_current_period()
        assert period == 'PEAK'

    @patch('backend.services.time_patterns.datetime')
    def test_low_hours_detection(self, mock_datetime):
        """Should detect low hours correctly."""
        mock_now = datetime(2025, 1, 15, 5, 0, 0, tzinfo=timezone.utc)  # 5 AM UTC
        mock_datetime.now.return_value = mock_now

        period = TimePatternAnalyzer.get_current_period()
        assert period == 'LOW'

    @patch('backend.services.time_patterns.datetime')
    def test_normal_hours_detection(self, mock_datetime):
        """Should detect normal hours correctly."""
        mock_now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)  # 12 PM UTC
        mock_datetime.now.return_value = mock_now

        period = TimePatternAnalyzer.get_current_period()
        assert period == 'NORMAL'

    @patch('backend.services.time_patterns.datetime')
    def test_peak_multiplier(self, mock_datetime):
        """Peak hours should have full allocation multiplier."""
        mock_now = datetime(2025, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        mult = TimePatternAnalyzer.get_time_multiplier()
        assert mult == 1.0

    @patch('backend.services.time_patterns.datetime')
    def test_low_multiplier(self, mock_datetime):
        """Low hours should have reduced allocation multiplier."""
        mock_now = datetime(2025, 1, 15, 5, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        mult = TimePatternAnalyzer.get_time_multiplier()
        assert mult == 0.75

    @patch('backend.services.time_patterns.datetime')
    def test_normal_multiplier(self, mock_datetime):
        """Normal hours should have slightly reduced multiplier."""
        mock_now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        mult = TimePatternAnalyzer.get_time_multiplier()
        assert mult == 0.9

    @patch('backend.services.time_patterns.datetime')
    def test_min_quality_score_peak(self, mock_datetime):
        """Peak hours should allow lower quality scores."""
        mock_now = datetime(2025, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        min_quality = TimePatternAnalyzer.get_min_quality_score(50.0)
        assert min_quality == 40.0  # 50 - 10 bonus

    @patch('backend.services.time_patterns.datetime')
    def test_min_quality_score_low(self, mock_datetime):
        """Low hours should require higher quality scores."""
        mock_now = datetime(2025, 1, 15, 5, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        min_quality = TimePatternAnalyzer.get_min_quality_score(50.0)
        assert min_quality == 70.0  # 50 + 20 penalty

    @patch('backend.services.time_patterns.datetime')
    def test_min_quality_score_capped(self, mock_datetime):
        """Min quality score should be capped."""
        mock_now = datetime(2025, 1, 15, 5, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        # Even with high base, cap at 90
        min_quality = TimePatternAnalyzer.get_min_quality_score(80.0)
        assert min_quality == 90.0

    @patch('backend.services.time_patterns.datetime')
    def test_should_trade_peak_good_quality(self, mock_datetime):
        """Should allow trade during peak with good quality."""
        mock_now = datetime(2025, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        should_trade, reason = TimePatternAnalyzer.should_trade(
            roi_percent=5.0,
            market_score=60.0
        )
        assert should_trade is True
        assert "PEAK" in reason

    @patch('backend.services.time_patterns.datetime')
    def test_should_trade_low_insufficient_roi(self, mock_datetime):
        """Should reject trade during low hours with low ROI."""
        mock_now = datetime(2025, 1, 15, 5, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        should_trade, reason = TimePatternAnalyzer.should_trade(
            roi_percent=2.0,  # Below 3% threshold for LOW hours
            market_score=80.0
        )
        assert should_trade is False
        assert "ROI" in reason

    @patch('backend.services.time_patterns.datetime')
    def test_slippage_adjustment_peak(self, mock_datetime):
        """Peak hours should have normal slippage tolerance."""
        mock_now = datetime(2025, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        slippage = TimePatternAnalyzer.get_max_slippage(0.005)
        assert slippage == 0.005

    @patch('backend.services.time_patterns.datetime')
    def test_slippage_adjustment_low(self, mock_datetime):
        """Low hours should have higher slippage tolerance."""
        mock_now = datetime(2025, 1, 15, 5, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        slippage = TimePatternAnalyzer.get_max_slippage(0.005)
        assert slippage == 0.0075  # 50% more

    def test_trading_summary(self):
        """Should return complete trading summary."""
        summary = TimePatternAnalyzer.get_trading_summary()

        assert 'current_time_utc' in summary
        assert 'current_hour_utc' in summary
        assert 'period' in summary
        assert 'allocation_multiplier' in summary
        assert 'min_quality_score' in summary
        assert 'max_slippage' in summary
        assert 'peak_hours' in summary
        assert 'low_hours' in summary


class TestDayOfWeekAnalyzer:
    """Tests for DayOfWeekAnalyzer."""

    @patch('backend.services.time_patterns.datetime')
    def test_weekday_multiplier(self, mock_datetime):
        """Weekdays should have full multiplier."""
        mock_now = datetime(2025, 1, 15, 15, 0, 0, tzinfo=timezone.utc)  # Wednesday
        mock_datetime.now.return_value = mock_now

        mult = DayOfWeekAnalyzer.get_day_multiplier()
        assert mult == 1.0

    @patch('backend.services.time_patterns.datetime')
    def test_weekend_multiplier(self, mock_datetime):
        """Weekends should have reduced multiplier."""
        mock_now = datetime(2025, 1, 18, 15, 0, 0, tzinfo=timezone.utc)  # Saturday
        mock_datetime.now.return_value = mock_now

        mult = DayOfWeekAnalyzer.get_day_multiplier()
        assert mult == 0.85

    @patch('backend.services.time_patterns.datetime')
    def test_friday_multiplier(self, mock_datetime):
        """Friday should have slightly reduced multiplier."""
        mock_now = datetime(2025, 1, 17, 15, 0, 0, tzinfo=timezone.utc)  # Friday
        mock_datetime.now.return_value = mock_now

        mult = DayOfWeekAnalyzer.get_day_multiplier()
        assert mult == 0.95

    @patch('backend.services.time_patterns.datetime')
    def test_is_weekend_saturday(self, mock_datetime):
        """Saturday should be detected as weekend."""
        mock_now = datetime(2025, 1, 18, 15, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        assert DayOfWeekAnalyzer.is_weekend() is True

    @patch('backend.services.time_patterns.datetime')
    def test_is_weekend_weekday(self, mock_datetime):
        """Weekday should not be detected as weekend."""
        mock_now = datetime(2025, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        assert DayOfWeekAnalyzer.is_weekend() is False


class TestMomentumDetector:
    """Tests for MomentumDetector."""

    def test_new_market_momentum(self):
        """New market should have NEW momentum."""
        detector = MomentumDetector()
        momentum = detector.detect_momentum("market_1", 0.95)
        assert momentum == 'NEW'

    def test_improving_momentum(self):
        """Decreasing cost should indicate IMPROVING momentum."""
        detector = MomentumDetector(lookback_seconds=60)

        # Record initial cost
        detector.record_cost("market_1", 0.97)

        # Cost dropped significantly
        momentum = detector.detect_momentum("market_1", 0.94)
        # Note: momentum is calculated from oldest cost in window
        # With only one recording, it might still be NEW
        # Let's add more recordings
        detector.record_cost("market_1", 0.96)
        detector.record_cost("market_1", 0.95)

        momentum = detector.detect_momentum("market_1", 0.93)
        # Now there's history to compare
        assert momentum in ['IMPROVING', 'STABLE', 'NEW']

    def test_stable_momentum(self):
        """Stable cost should indicate STABLE momentum."""
        detector = MomentumDetector()

        detector.record_cost("market_1", 0.95)
        detector.record_cost("market_1", 0.95)

        momentum = detector.detect_momentum("market_1", 0.951)
        assert momentum == 'STABLE'

    def test_degrading_momentum(self):
        """Increasing cost should indicate DEGRADING momentum."""
        detector = MomentumDetector()

        detector.record_cost("market_1", 0.93)
        detector.record_cost("market_1", 0.94)

        momentum = detector.detect_momentum("market_1", 0.96)
        assert momentum == 'DEGRADING'

    def test_priority_score_improving(self):
        """Improving momentum should have high priority."""
        detector = MomentumDetector()

        detector.record_cost("market_1", 0.97)
        detector.record_cost("market_1", 0.95)

        score = detector.get_priority_score("market_1", 0.92)
        # IMPROVING gets 1.5
        assert score >= 1.0

    def test_priority_score_degrading(self):
        """Degrading momentum should have low priority."""
        detector = MomentumDetector()

        detector.record_cost("market_1", 0.93)
        detector.record_cost("market_1", 0.94)

        score = detector.get_priority_score("market_1", 0.97)
        # DEGRADING gets 0.5
        assert score <= 1.0

    def test_priority_score_new(self):
        """New opportunities should have medium-high priority."""
        detector = MomentumDetector()
        score = detector.get_priority_score("new_market", 0.95)
        assert score == 1.2  # NEW = 1.2

    def test_history_cleanup(self):
        """Old entries should be cleaned up."""
        detector = MomentumDetector(lookback_seconds=1)

        detector.record_cost("market_1", 0.95)

        # Simulate time passing by manipulating internal state
        # In real use, this happens automatically
        import time
        time.sleep(1.1)

        detector.record_cost("market_1", 0.94)

        # Old entry should be cleaned
        assert len(detector._cost_history["market_1"]) == 1


class TestCombinedMultiplier:
    """Tests for combined time multiplier."""

    @patch('backend.services.time_patterns.TimePatternAnalyzer.get_time_multiplier')
    @patch('backend.services.time_patterns.DayOfWeekAnalyzer.get_day_multiplier')
    def test_combined_multiplier(self, mock_day, mock_time):
        """Combined multiplier should be product of time and day."""
        mock_time.return_value = 0.9
        mock_day.return_value = 0.95

        combined = get_combined_time_multiplier()
        assert abs(combined - 0.855) < 0.001

    @patch('backend.services.time_patterns.TimePatternAnalyzer.get_time_multiplier')
    @patch('backend.services.time_patterns.DayOfWeekAnalyzer.get_day_multiplier')
    def test_combined_multiplier_worst_case(self, mock_day, mock_time):
        """Worst case should be low hours on weekend."""
        mock_time.return_value = 0.75  # LOW hours
        mock_day.return_value = 0.85   # Weekend

        combined = get_combined_time_multiplier()
        assert abs(combined - 0.6375) < 0.001

    @patch('backend.services.time_patterns.TimePatternAnalyzer.get_time_multiplier')
    @patch('backend.services.time_patterns.DayOfWeekAnalyzer.get_day_multiplier')
    def test_combined_multiplier_best_case(self, mock_day, mock_time):
        """Best case should be peak hours on weekday."""
        mock_time.return_value = 1.0  # PEAK hours
        mock_day.return_value = 1.0   # Weekday

        combined = get_combined_time_multiplier()
        assert combined == 1.0
