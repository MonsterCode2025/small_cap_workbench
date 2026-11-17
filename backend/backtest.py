"""回测引擎：集成选股、组合管理和历史模拟。

对应设计文档第6节：账户回测与验证。
"""
from __future__ import annotations

import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Literal

from .data import UniverseBuilder, fetch_daily_quotes, calculate_adv20
from .selection import SmallCapSelector, SelectionConfig
from .portfolio import Portfolio, FeeConfig


class BacktestEngine:
    """回测引擎。"""

    def __init__(
        self,
        selection_config: SelectionConfig | None = None,
        fee_config: FeeConfig | None = None,
        initial_cash: float = 1_000_000,
        slippage_bps: float = 5.0
    ):
        self.selector = SmallCapSelector(selection_config)
        self.portfolio = Portfolio(initial_cash, fee_config, slippage_bps)
        self.selection_config = selection_config or SelectionConfig()

    def run(
        self,
        trading_dates: list[str],
        universe_data: dict[str, pd.DataFrame],  # {date: universe_df}
        market_data: dict[str, dict[str, pd.DataFrame]],  # {symbol: quotes_df}
        start_date: str,
        end_date: str
    ) -> dict:
        """执行回测。

        Args:
            trading_dates: 交易日列表
            universe_data: 每日股票池数据
            market_data: 市场行情数据
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            回测结果字典
        """
        # 获取月末日期
        builder = UniverseBuilder(pd.DataFrame({"trade_date": pd.to_datetime(trading_dates)}))
        month_ends = builder.get_month_ends(start_date, end_date)

        # 初始化
        rebalance_dates = {me: trading_dates[trading_dates.index(me) + 1]
                          for me in month_ends if trading_dates.index(me) < len(trading_dates) - 1}

        current_targets = {}

        # 主循环
        for date in trading_dates:
            if date < start_date:
                continue
            if date > end_date:
                break

            # 检查是否是调仓日的次日（执行日）
            signal_date = None
            for me, exec_date in rebalance_dates.items():
                if date == exec_date:
                    signal_date = me
                    break

            if signal_date:
                # 执行调仓逻辑
                universe = universe_data.get(signal_date, pd.DataFrame())

                # 收集市值、ADV20等数据
                market_caps = {}
                adv20_values = {}
                close_prices = {}

                for symbol in universe["symbol"]:
                    quotes = market_data.get(symbol)
                    if quotes is not None and not quotes.empty:
                        signal_quotes = quotes[quotes["date"] <= signal_date]
                        if not signal_quotes.empty:
                            last_row = signal_quotes.iloc[-1]
                            close_prices[symbol] = float(last_row["close"])

                            # 简化市值计算：假设从行情推算
                            market_caps[symbol] = float(last_row.get("market_cap", last_row["close"] * 1e8))

                            # 计算ADV20
                            adv20_values[symbol] = calculate_adv20(signal_quotes, signal_date)

                # 执行选股
                candidates, stats = self.selector.select(
                    universe=universe,
                    market_caps=market_caps,
                    adv20_values=adv20_values,
                    prices=close_prices
                )

                # 计算目标持仓
                weights = self.selector.compute_target_weights(candidates)
                equity = self.portfolio.compute_equity(close_prices)
                current_targets = self.selector.compute_target_shares(candidates, weights, equity)

                # 收集执行日数据
                open_prices = {}
                for symbol in set(list(current_targets.keys()) + list(self.portfolio.positions.keys())):
                    quotes = market_data.get(symbol)
                    if quotes is not None:
                        exec_quotes = quotes[quotes["date"] == date]
                        if not exec_quotes.empty:
                            open_prices[symbol] = float(exec_quotes.iloc[0]["open"])

                # 执行调仓
                self.portfolio.execute_rebalance(
                    signal_date=signal_date,
                    execution_date=date,
                    target_shares=current_targets,
                    prices=open_prices
                )

            # 收集收盘价并记录状态
            close_prices = {}
            for symbol in self.portfolio.positions.keys():
                quotes = market_data.get(symbol)
                if quotes is not None:
                    day_quotes = quotes[quotes["date"] == date]
                    if not day_quotes.empty:
                        close_prices[symbol] = float(day_quotes.iloc[0]["close"])

            self.portfolio.record_state(date, close_prices)

        # 生成结果
        summary = self.portfolio.get_summary()

        equity_records = [
            {
                "date": s.date,
                "equity": s.equity,
                "cash": s.cash,
                "drawdown": s.drawdown,
                "positions": len(s.positions)
            }
            for s in self.portfolio.equity_history
        ]

        trade_records = [
            {
                "date": t.date,
                "symbol": t.symbol,
                "side": t.side,
                "shares": t.shares,
                "price": t.price,
                "amount": t.amount,
                "fees": t.fees,
                "realized_pnl": t.realized_pnl
            }
            for t in self.portfolio.trade_history
        ]

        order_records = [
            {
                "date": o.date,
                "signal_date": o.signal_date,
                "symbol": o.symbol,
                "side": o.side,
                "target_shares": o.target_shares,
                "filled_shares": o.filled_shares,
                "status": o.status,
                "reason": o.reason
            }
            for o in self.portfolio.order_history
        ]

        return {
            "summary": summary,
            "equity": equity_records,
            "trades": trade_records,
            "orders": order_records,
            "config": {
                "selection": self.selection_config.__dict__,
                "initial_cash": self.portfolio.initial_cash,
                "slippage_bps": self.portfolio.slippage_bps
            }
        }
