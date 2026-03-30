"""
Weight Adjuster Module

Adjusts indicator weights based on performance analysis.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

INDICATOR_MAP = {
    'rsi_score': 'rsi',
    'macd_score': 'macd',
    'volume_score': 'volume',
    'support_score': 'support',
}


class WeightAdjuster:
    """Adjust indicator weights based on observed performance."""

    def __init__(
        self,
        current_weights: Dict[str, float],
        history_file: str = 'weight_history.json',
        min_weight: float = 0.10,
        max_adjustment: float = 0.05,
        min_outcomes_for_adjustment: int = 20,
        auto_apply: bool = False,
    ):
        self.current_weights = dict(current_weights)
        self.history_file = Path(history_file)
        self.min_weight = min_weight
        self.max_adjustment = max_adjustment
        self.min_outcomes_for_adjustment = min_outcomes_for_adjustment
        self.auto_apply = auto_apply

        self.history: List[Dict] = []
        self._load_history()

    def calculate_adjusted_weights(
        self,
        analysis: Dict,
    ) -> Optional[Dict]:
        """
        Calculate new weights based on performance analysis.

        Returns a dict with 'weights', 'reasoning', 'applied' keys,
        or None if insufficient data.
        """
        effectiveness = analysis.get('indicator_effectiveness', {})
        sample_size = analysis.get('sample_size', 0)

        if sample_size < self.min_outcomes_for_adjustment:
            logger.info(
                f"Insufficient outcomes for weight adjustment: "
                f"{sample_size}/{self.min_outcomes_for_adjustment}"
            )
            return None

        # Check minimum samples per group
        for key, data in effectiveness.items():
            if data['high_score_count'] < 5 or data['low_score_count'] < 5:
                logger.info(
                    f"Insufficient per-group samples for {data['name']}: "
                    f"high={data['high_score_count']}, low={data['low_score_count']}"
                )
                return None

        new_weights = dict(self.current_weights)
        reasoning = {}
        deadzone = 0.10

        for score_key, weight_key in INDICATOR_MAP.items():
            data = effectiveness.get(score_key)
            if data is None:
                reasoning[weight_key] = 'No data'
                continue

            lift = data['lift']
            old_weight = self.current_weights.get(weight_key, 0.25)

            if lift > deadzone:
                raw_adj = lift * 0.10
                adj = min(raw_adj, self.max_adjustment)
                new_weights[weight_key] = old_weight + adj
                reasoning[weight_key] = (
                    f"Lift {lift*100:+.1f}pp > deadzone, "
                    f"increase {old_weight:.2f} -> {new_weights[weight_key]:.3f}"
                )
            elif lift < -deadzone:
                raw_adj = lift * 0.10  # negative
                adj = max(raw_adj, -self.max_adjustment)
                new_weights[weight_key] = old_weight + adj
                reasoning[weight_key] = (
                    f"Lift {lift*100:+.1f}pp < -deadzone, "
                    f"decrease {old_weight:.2f} -> {new_weights[weight_key]:.3f}"
                )
            else:
                reasoning[weight_key] = (
                    f"Lift {lift*100:+.1f}pp within deadzone, no change"
                )

        # Apply floor
        for key in new_weights:
            new_weights[key] = max(new_weights[key], self.min_weight)

        # Normalize to sum to 1.0
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {k: v / total for k, v in new_weights.items()}

        # Round for cleanliness
        new_weights = {k: round(v, 4) for k, v in new_weights.items()}

        applied = False
        if self.auto_apply:
            self.current_weights = dict(new_weights)
            applied = True
            logger.info(f"Auto-applied new weights: {new_weights}")
        else:
            logger.info(f"Suggested new weights (not applied): {new_weights}")

        # Save to history
        entry = {
            'timestamp': datetime.now().isoformat(),
            'previous_weights': dict(self.current_weights) if not applied else None,
            'new_weights': new_weights,
            'reasoning': reasoning,
            'sample_size': sample_size,
            'applied': applied,
        }
        # Fix: if applied, previous_weights was overwritten, reconstruct
        if applied:
            entry['previous_weights'] = {
                k: round(v, 4) for k, v in
                (self.history[-1]['new_weights'] if self.history else self.current_weights).items()
            }
        self.history.append(entry)
        self._save_history()

        return {
            'weights': new_weights,
            'reasoning': reasoning,
            'applied': applied,
        }

    def revert_to_previous(self) -> Optional[Dict[str, float]]:
        """Revert to the most recent previous weights."""
        if not self.history:
            logger.warning("No weight history to revert to")
            return None

        last_entry = self.history[-1]
        previous = last_entry.get('previous_weights')

        if previous is None:
            logger.warning("No previous weights in last history entry")
            return None

        self.current_weights = dict(previous)
        logger.info(f"Reverted weights to: {self.current_weights}")

        revert_entry = {
            'timestamp': datetime.now().isoformat(),
            'previous_weights': last_entry.get('new_weights'),
            'new_weights': dict(previous),
            'reasoning': {'action': 'revert'},
            'sample_size': 0,
            'applied': True,
        }
        self.history.append(revert_entry)
        self._save_history()

        return dict(self.current_weights)

    def get_current_weights(self) -> Dict[str, float]:
        return dict(self.current_weights)

    def format_adjustment_html(self, result: Dict) -> str:
        """Format weight adjustment result as HTML for Telegram."""
        weights = result['weights']
        reasoning = result['reasoning']
        applied = result['applied']

        status = "APPLIED" if applied else "SUGGESTED (review required)"

        lines = [
            f"<b>Weight Adjustment - {status}</b>",
            "",
        ]

        for key in ['rsi', 'macd', 'volume', 'support']:
            new_w = weights.get(key, 0)
            lines.append(f"  {key.upper()}: {new_w*100:.1f}%")

        lines.append("")
        lines.append("<b>Reasoning:</b>")
        for key, reason in reasoning.items():
            lines.append(f"  {key.upper()}: {reason}")

        return "\n".join(lines)

    def _load_history(self) -> None:
        if not self.history_file.exists():
            return
        try:
            with open(self.history_file, 'r') as f:
                self.history = json.load(f)
            logger.debug(f"Loaded {len(self.history)} weight history entries")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Could not load weight history: {e}")

    def _save_history(self) -> None:
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, indent=2)
        except IOError as e:
            logger.warning(f"Could not save weight history: {e}")
