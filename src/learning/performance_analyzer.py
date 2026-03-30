"""
Performance Analyzer Module

Analyzes completed outcomes to measure indicator effectiveness.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

INDICATOR_KEYS = ['rsi_score', 'macd_score', 'volume_score', 'support_score']
INDICATOR_NAMES = {
    'rsi_score': 'RSI',
    'macd_score': 'MACD',
    'volume_score': 'Volume',
    'support_score': 'Support',
}


class PerformanceAnalyzer:
    """Analyze completed outcomes to assess indicator effectiveness."""

    def __init__(self, min_outcomes: int = 10):
        self.min_outcomes = min_outcomes

    def analyze(self, completed: List[Dict], market: Optional[str] = None) -> Optional[Dict]:
        """
        Run full performance analysis on completed outcomes.

        Args:
            completed: List of completed outcome dicts
            market: Optional market ID to filter by (e.g. 'sp500', 'ftse100')

        Returns None if insufficient data.
        """
        if market:
            completed = [o for o in completed if o.get('market') == market]

        if len(completed) < self.min_outcomes:
            logger.info(
                f"Insufficient outcomes for analysis: "
                f"{len(completed)}/{self.min_outcomes}"
            )
            return None

        overall = self._calculate_overall_stats(completed)
        indicator_effectiveness = self._calculate_indicator_effectiveness(completed)
        prediction_accuracy = self._calculate_prediction_accuracy(completed)

        return {
            'overall': overall,
            'indicator_effectiveness': indicator_effectiveness,
            'prediction_accuracy': prediction_accuracy,
            'sample_size': len(completed),
            'analyzed_at': datetime.now().isoformat(),
        }

    def _calculate_overall_stats(self, completed: List[Dict]) -> Dict:
        """Calculate win rate, average return, etc."""
        wins = [o for o in completed if o.get('actual_return_pct', 0) > 0]
        returns = [o.get('actual_return_pct', 0) for o in completed]
        days_held = [o.get('days_held', 0) for o in completed]

        hit_tp = [o for o in completed if o.get('outcome') == 'hit_tp']
        hit_sl = [o for o in completed if o.get('outcome') == 'hit_sl']
        expired = [o for o in completed if o.get('outcome') == 'expired']

        return {
            'total': len(completed),
            'win_rate': len(wins) / len(completed),
            'avg_return_pct': sum(returns) / len(returns),
            'avg_days_held': sum(days_held) / len(days_held) if days_held else 0,
            'hit_tp_count': len(hit_tp),
            'hit_sl_count': len(hit_sl),
            'expired_count': len(expired),
            'best_return_pct': max(returns) if returns else 0,
            'worst_return_pct': min(returns) if returns else 0,
        }

    def _calculate_indicator_effectiveness(self, completed: List[Dict]) -> Dict:
        """
        For each indicator, compare win rate when score is high vs low.

        The "lift" measures how predictive that indicator is.
        """
        results = {}

        for key in INDICATOR_KEYS:
            name = INDICATOR_NAMES[key]
            high_group = [o for o in completed if o.get(key, 0) >= 50]
            low_group = [o for o in completed if o.get(key, 0) < 50]

            high_wins = len([o for o in high_group if o.get('actual_return_pct', 0) > 0])
            low_wins = len([o for o in low_group if o.get('actual_return_pct', 0) > 0])

            high_win_rate = high_wins / len(high_group) if high_group else 0
            low_win_rate = low_wins / len(low_group) if low_group else 0

            lift = high_win_rate - low_win_rate

            high_returns = [o.get('actual_return_pct', 0) for o in high_group]
            low_returns = [o.get('actual_return_pct', 0) for o in low_group]

            results[key] = {
                'name': name,
                'high_score_count': len(high_group),
                'low_score_count': len(low_group),
                'high_score_win_rate': high_win_rate,
                'low_score_win_rate': low_win_rate,
                'lift': lift,
                'high_score_avg_return': sum(high_returns) / len(high_returns) if high_returns else 0,
                'low_score_avg_return': sum(low_returns) / len(low_returns) if low_returns else 0,
            }

        return results

    def _calculate_prediction_accuracy(self, completed: List[Dict]) -> Dict:
        """Compare predicted vs actual take-profit hit rate and timing."""
        with_tp = [o for o in completed if o.get('take_profit_pct') is not None]

        if not with_tp:
            return {'predicted_tp_count': 0}

        actual_hits = [o for o in with_tp if o.get('outcome') == 'hit_tp']
        tp_hit_rate = len(actual_hits) / len(with_tp)

        # Compare predicted vs actual days for tp hits
        days_predictions = []
        for o in actual_hits:
            predicted = o.get('estimated_days_to_target')
            actual = o.get('days_held')
            if predicted and actual:
                days_predictions.append({
                    'predicted': predicted,
                    'actual': actual,
                    'error': actual - predicted,
                })

        avg_days_error = 0
        if days_predictions:
            avg_days_error = sum(d['error'] for d in days_predictions) / len(days_predictions)

        return {
            'predicted_tp_count': len(with_tp),
            'actual_tp_hits': len(actual_hits),
            'tp_hit_rate': tp_hit_rate,
            'avg_days_prediction_error': avg_days_error,
        }

    def format_report_html(self, analysis: Dict) -> str:
        """Format analysis results as HTML for Telegram."""
        overall = analysis['overall']
        effectiveness = analysis['indicator_effectiveness']
        prediction = analysis['prediction_accuracy']

        lines = [
            "<b>Performance Report</b>",
            "",
            f"<b>Overall ({overall['total']} trades)</b>",
            f"Win Rate: {overall['win_rate']*100:.1f}%",
            f"Avg Return: {overall['avg_return_pct']*100:+.1f}%",
            f"Avg Days Held: {overall['avg_days_held']:.0f}",
            f"TP Hits: {overall['hit_tp_count']} | SL Hits: {overall['hit_sl_count']} | Expired: {overall['expired_count']}",
            f"Best: {overall['best_return_pct']*100:+.1f}% | Worst: {overall['worst_return_pct']*100:+.1f}%",
            "",
            "<b>Indicator Effectiveness</b>",
        ]

        for key in INDICATOR_KEYS:
            e = effectiveness[key]
            lift_str = f"{e['lift']*100:+.1f}pp"
            lines.append(
                f"{e['name']}: lift {lift_str} "
                f"(high {e['high_score_win_rate']*100:.0f}% vs low {e['low_score_win_rate']*100:.0f}%, "
                f"n={e['high_score_count']}/{e['low_score_count']})"
            )

        if prediction.get('predicted_tp_count', 0) > 0:
            lines.extend([
                "",
                "<b>Prediction Accuracy</b>",
                f"TP Hit Rate: {prediction['tp_hit_rate']*100:.1f}% ({prediction['actual_tp_hits']}/{prediction['predicted_tp_count']})",
            ])
            if prediction.get('avg_days_prediction_error') is not None:
                lines.append(f"Days Estimate Error: {prediction['avg_days_prediction_error']:+.1f}d avg")

        return "\n".join(lines)

    def is_report_day(self, day_name: str = 'fri') -> bool:
        """Check if today is the weekly report day."""
        today = datetime.now().strftime('%a').lower()
        return today == day_name[:3].lower()
