from __future__ import annotations
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Backtest:
    """
    Simple backtesting framework for swing trading strategy.
    Simulates weekly screening and tracks trade outcomes.
    """

    def __init__(self, initial_capital: float = 1000000, max_positions: int = 10):
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.capital_per_trade = initial_capital / max_positions

        self.trades = []
        self.equity_curve = []

    def simulate_trade_outcome(self, entry: float, stop: float, target: float,
                               future_prices: pd.DataFrame) -> dict:
        """
        Simulate a single trade outcome given future price data.
        Returns: {exit_price, exit_reason, return_pct, bars_held}
        """
        if future_prices.empty:
            return {
                "exit_price": entry,
                "exit_reason": "no_data",
                "return_pct": 0.0,
                "bars_held": 0
            }

        for idx, (_, row) in enumerate(future_prices.iterrows()):
            bars_held = idx + 1

            # Check stop loss hit
            if row["low"] <= stop:
                return {
                    "exit_price": stop,
                    "exit_reason": "stop_loss",
                    "return_pct": ((stop - entry) / entry) * 100,
                    "bars_held": bars_held
                }

            # Check target hit
            if row["high"] >= target:
                return {
                    "exit_price": target,
                    "exit_reason": "target",
                    "return_pct": ((target - entry) / entry) * 100,
                    "bars_held": bars_held
                }

            # Exit after 10 days if neither hit
            if bars_held >= 10:
                exit_price = row["close"]
                return {
                    "exit_price": exit_price,
                    "exit_reason": "time_exit",
                    "return_pct": ((exit_price - entry) / entry) * 100,
                    "bars_held": bars_held
                }

        # Ran out of data
        last_close = future_prices.iloc[-1]["close"]
        return {
            "exit_price": last_close,
            "exit_reason": "data_end",
            "return_pct": ((last_close - entry) / entry) * 100,
            "bars_held": len(future_prices)
        }

    def run(self, screener_results: pd.DataFrame, all_price_data: pd.DataFrame,
            screening_date: str) -> dict:
        """
        Run backtest for a single screening date.

        Args:
            screener_results: Output from screener (top candidates)
            all_price_data: Complete price history for calculating outcomes
            screening_date: Date when screening was performed

        Returns:
            Summary statistics for this screening period
        """
        trades_this_week = []

        for _, candidate in screener_results.iterrows():
            symbol = candidate["symbol"]
            entry = candidate["entry_price"]
            stop = candidate["stop_loss"]
            target = candidate["target_price"]

            # Get future price data for this symbol (next 10 days after screening)
            symbol_data = all_price_data[
                (all_price_data["symbol"] == symbol) &
                (all_price_data["trade_date"] > screening_date)
            ].sort_values("trade_date").head(10)

            # Simulate trade
            outcome = self.simulate_trade_outcome(entry, stop, target, symbol_data)

            trade_record = {
                "symbol": symbol,
                "entry_date": screening_date,
                "entry_price": entry,
                "stop_loss": stop,
                "target_price": target,
                "exit_price": outcome["exit_price"],
                "exit_reason": outcome["exit_reason"],
                "return_pct": outcome["return_pct"],
                "bars_held": outcome["bars_held"]
            }

            trades_this_week.append(trade_record)
            self.trades.append(trade_record)

        # Calculate weekly summary
        if trades_this_week:
            returns = [t["return_pct"] for t in trades_this_week]
            summary = {
                "screening_date": screening_date,
                "num_trades": len(trades_this_week),
                "avg_return": np.mean(returns),
                "median_return": np.median(returns),
                "win_rate": len([r for r in returns if r > 0]) / len(returns) * 100,
                "best_trade": max(returns),
                "worst_trade": min(returns)
            }
        else:
            summary = {
                "screening_date": screening_date,
                "num_trades": 0,
                "avg_return": 0,
                "median_return": 0,
                "win_rate": 0,
                "best_trade": 0,
                "worst_trade": 0
            }

        return summary

    def get_overall_stats(self) -> dict:
        """Calculate overall backtest statistics"""
        if not self.trades:
            return {
                "total_trades": 0,
                "avg_return": 0,
                "win_rate": 0,
                "profit_factor": 0,
                "max_drawdown": 0
            }

        returns = [t["return_pct"] for t in self.trades]
        winning_trades = [r for r in returns if r > 0]
        losing_trades = [r for r in returns if r < 0]

        total_profit = sum(winning_trades)
        total_loss = abs(sum(losing_trades))

        stats = {
            "total_trades": len(self.trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": (len(winning_trades) / len(self.trades)) * 100 if self.trades else 0,
            "avg_return": np.mean(returns),
            "median_return": np.median(returns),
            "best_trade": max(returns),
            "worst_trade": min(returns),
            "profit_factor": total_profit / total_loss if total_loss > 0 else float('inf'),
            "avg_bars_held": np.mean([t["bars_held"] for t in self.trades]),
            "target_hit_rate": len([t for t in self.trades if t["exit_reason"] == "target"]) / len(self.trades) * 100,
            "stop_hit_rate": len([t for t in self.trades if t["exit_reason"] == "stop_loss"]) / len(self.trades) * 100
        }

        return stats

    def get_trades_dataframe(self) -> pd.DataFrame:
        """Return all trades as DataFrame"""
        return pd.DataFrame(self.trades)
