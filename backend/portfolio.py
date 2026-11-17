"""组合账户模块：多股票持仓、调仓执行、费用计算。

对应设计文档第3.3节和第6.1节：调仓、异常与实际持仓。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

import pandas as pd
import numpy as np


def money(value: float) -> float:
    """金额四舍五入到分。"""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@dataclass
class FeeConfig:
    """费用配置。"""
    commission_rate: float = 0.0003  # 佣金费率
    min_commission: float = 5.0  # 最低佣金
    stamp_tax_rate: float = 0.0005  # 印花税率（仅卖出，2023-08-28起）
    transfer_fee_rate: float = 0.00001  # 过户费率

    def calculate(self, amount: float, side: Literal["buy", "sell"], date: str) -> dict:
        """计算交易费用。

        Args:
            amount: 成交金额
            side: 买卖方向
            date: 交易日期 YYYY-MM-DD

        Returns:
            费用明细字典
        """
        commission = money(max(self.min_commission, amount * self.commission_rate))

        # 印花税：2023-08-28起为0.05%，之前为0.1%
        if side == "sell":
            if date >= "2023-08-28":
                stamp = money(amount * 0.0005)
            else:
                stamp = money(amount * 0.001)
        else:
            stamp = 0.0

        transfer = money(amount * self.transfer_fee_rate)

        return {
            "commission": commission,
            "stamp": stamp,
            "transfer": transfer,
            "total": money(commission + stamp + transfer)
        }


@dataclass
class Position:
    """持仓信息。"""
    symbol: str
    shares: int
    cost_basis: float  # 成本基础（含买入费用）
    last_buy_date: str = ""  # 最后买入日期（用于T+1检查）


@dataclass
class Order:
    """订单记录。"""
    date: str  # 执行日期
    signal_date: str  # 信号日期
    symbol: str
    side: Literal["buy", "sell"]
    target_shares: int
    filled_shares: int
    price: float
    amount: float
    fees: float
    status: Literal["filled", "rejected", "partial"]
    reason: str = ""


@dataclass
class Trade:
    """成交记录。"""
    date: str
    symbol: str
    side: Literal["buy", "sell"]
    shares: int
    price: float
    amount: float
    fees: float
    realized_pnl: float | None = None  # 仅卖出时有效


@dataclass
class PortfolioState:
    """组合状态快照。"""
    date: str
    equity: float
    cash: float
    positions: list[Position]
    market_values: dict[str, float]  # {symbol: value}
    drawdown: float = 0.0
    peak_equity: float = 0.0


class Portfolio:
    """多股票组合账户。

    实现设计文档第6.1节的账户逻辑。
    """

    def __init__(
        self,
        initial_cash: float,
        fee_config: FeeConfig | None = None,
        slippage_bps: float = 5.0
    ):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: dict[str, Position] = {}
        self.fee_config = fee_config or FeeConfig()
        self.slippage_bps = slippage_bps

        self.equity_history: list[PortfolioState] = []
        self.trade_history: list[Trade] = []
        self.order_history: list[Order] = []

        self.peak_equity = initial_cash
        self.current_date = ""

    def get_position_shares(self, symbol: str) -> int:
        """获取持仓股数。"""
        return self.positions.get(symbol, Position(symbol, 0, 0.0)).shares

    def compute_equity(self, prices: dict[str, float]) -> float:
        """计算当前权益。"""
        stock_value = sum(
            pos.shares * prices.get(pos.symbol, 0)
            for pos in self.positions.values()
        )
        return money(self.cash + stock_value)

    def execute_rebalance(
        self,
        signal_date: str,
        execution_date: str,
        target_shares: dict[str, int],
        prices: dict[str, float],
        limits: dict[str, tuple[float, float]] | None = None,
        trading_status: dict[str, str] | None = None,
    ) -> dict:
        """执行调仓。

        Args:
            signal_date: 信号生成日期（前一交易日）
            execution_date: 执行日期（当前交易日）
            target_shares: 目标持仓 {symbol: shares}
            prices: 开盘价 {symbol: price}
            limits: 涨跌停价 {symbol: (lower, upper)}
            trading_status: 交易状态 {symbol: status}

        Returns:
            执行统计信息
        """
        self.current_date = execution_date
        limits = limits or {}
        trading_status = trading_status or {}

        stats = {
            "orders": 0,
            "filled": 0,
            "rejected": 0,
            "buy_amount": 0.0,
            "sell_amount": 0.0,
        }

        # 第一步：先卖出
        sell_orders = []
        for symbol, pos in list(self.positions.items()):
            target = target_shares.get(symbol, 0)
            if target < pos.shares:
                sell_orders.append((symbol, pos.shares - target))

        for symbol, sell_shares in sell_orders:
            self._execute_sell(
                symbol, sell_shares, signal_date, execution_date,
                prices, limits, trading_status, stats
            )

        # 第二步：再买入
        buy_orders = []
        for symbol, target in target_shares.items():
            current = self.get_position_shares(symbol)
            if target > current:
                buy_orders.append((symbol, target - current))

        # 按信号日的候选排序买入
        for symbol, buy_shares in buy_orders:
            self._execute_buy(
                symbol, buy_shares, signal_date, execution_date,
                prices, limits, trading_status, stats
            )

        return stats

    def _execute_sell(
        self,
        symbol: str,
        shares: int,
        signal_date: str,
        execution_date: str,
        prices: dict[str, float],
        limits: dict[str, tuple[float, float]],
        trading_status: dict[str, str],
        stats: dict
    ):
        """执行卖出。"""
        stats["orders"] += 1

        price = prices.get(symbol)
        if price is None:
            self._reject_order(signal_date, execution_date, symbol, "sell", shares, "无开盘价")
            stats["rejected"] += 1
            return

        # 检查涨跌停
        lower, upper = limits.get(symbol, (0, float("inf")))
        if price <= lower + 1e-8:
            self._reject_order(signal_date, execution_date, symbol, "sell", shares, "开盘触及跌停价")
            stats["rejected"] += 1
            return

        # 检查停牌
        if trading_status.get(symbol, "trading") != "trading":
            self._reject_order(signal_date, execution_date, symbol, "sell", shares, "停牌")
            stats["rejected"] += 1
            return

        # 检查T+1
        pos = self.positions.get(symbol)
        if pos and pos.last_buy_date >= execution_date:
            self._reject_order(signal_date, execution_date, symbol, "sell", shares, "T+1限制")
            stats["rejected"] += 1
            return

        # 应用滑点
        slipped_price = money(price * (1 - self.slippage_bps / 10000))
        slipped_price = max(slipped_price, lower)

        amount = money(shares * slipped_price)
        fees = self.fee_config.calculate(amount, "sell", execution_date)

        # 检查费用
        proceeds = money(amount - fees["total"])
        if self.cash + proceeds < 0:
            self._reject_order(signal_date, execution_date, symbol, "sell", shares, "费用超过可用现金")
            stats["rejected"] += 1
            return

        # 执行卖出
        if pos:
            realized_pnl = money(proceeds - (pos.cost_basis * shares / pos.shares))
            new_shares = pos.shares - shares
            if new_shares > 0:
                new_cost = money(pos.cost_basis * new_shares / pos.shares)
                self.positions[symbol] = Position(symbol, new_shares, new_cost, pos.last_buy_date)
            else:
                del self.positions[symbol]

            self.cash = money(self.cash + proceeds)

            self.trade_history.append(Trade(
                date=execution_date,
                symbol=symbol,
                side="sell",
                shares=shares,
                price=slipped_price,
                amount=amount,
                fees=fees["total"],
                realized_pnl=realized_pnl
            ))

            self.order_history.append(Order(
                date=execution_date,
                signal_date=signal_date,
                symbol=symbol,
                side="sell",
                target_shares=shares,
                filled_shares=shares,
                price=slipped_price,
                amount=amount,
                fees=fees["total"],
                status="filled",
                reason="按前日目标在开盘成交"
            ))

            stats["filled"] += 1
            stats["sell_amount"] += amount

    def _execute_buy(
        self,
        symbol: str,
        shares: int,
        signal_date: str,
        execution_date: str,
        prices: dict[str, float],
        limits: dict[str, tuple[float, float]],
        trading_status: dict[str, str],
        stats: dict
    ):
        """执行买入。"""
        stats["orders"] += 1

        price = prices.get(symbol)
        if price is None:
            self._reject_order(signal_date, execution_date, symbol, "buy", shares, "无开盘价")
            stats["rejected"] += 1
            return

        # 检查涨跌停
        lower, upper = limits.get(symbol, (0, float("inf")))
        if price >= upper - 1e-8:
            self._reject_order(signal_date, execution_date, symbol, "buy", shares, "开盘触及涨停价")
            stats["rejected"] += 1
            return

        # 检查停牌
        if trading_status.get(symbol, "trading") != "trading":
            self._reject_order(signal_date, execution_date, symbol, "buy", shares, "停牌")
            stats["rejected"] += 1
            return

        # 应用滑点
        slipped_price = money(price * (1 + self.slippage_bps / 10000))
        slipped_price = min(slipped_price, upper)

        # 计算可买股数（整手）
        buyable_shares = 0
        for test_shares in range(shares, -100, -100):
            if test_shares <= 0:
                break
            amount = money(test_shares * slipped_price)
            fees = self.fee_config.calculate(amount, "buy", execution_date)
            total_cost = money(amount + fees["total"])
            if total_cost <= self.cash:
                buyable_shares = test_shares
                break

        if buyable_shares == 0:
            self._reject_order(signal_date, execution_date, symbol, "buy", shares, "预算不足")
            stats["rejected"] += 1
            return

        # 执行买入
        amount = money(buyable_shares * slipped_price)
        fees = self.fee_config.calculate(amount, "buy", execution_date)
        total_cost = money(amount + fees["total"])

        self.cash = money(self.cash - total_cost)

        if symbol in self.positions:
            pos = self.positions[symbol]
            new_shares = pos.shares + buyable_shares
            new_cost = money(pos.cost_basis + total_cost)
            self.positions[symbol] = Position(symbol, new_shares, new_cost, execution_date)
        else:
            self.positions[symbol] = Position(symbol, buyable_shares, total_cost, execution_date)

        self.trade_history.append(Trade(
            date=execution_date,
            symbol=symbol,
            side="buy",
            shares=buyable_shares,
            price=slipped_price,
            amount=amount,
            fees=fees["total"]
        ))

        self.order_history.append(Order(
            date=execution_date,
            signal_date=signal_date,
            symbol=symbol,
            side="buy",
            target_shares=shares,
            filled_shares=buyable_shares,
            price=slipped_price,
            amount=amount,
            fees=fees["total"],
            status="filled" if buyable_shares == shares else "partial",
            reason="按前日目标在开盘成交" if buyable_shares == shares else f"预算限制，仅买入{buyable_shares}/{shares}股"
        ))

        stats["filled"] += 1
        stats["buy_amount"] += amount

    def _reject_order(
        self,
        signal_date: str,
        execution_date: str,
        symbol: str,
        side: str,
        shares: int,
        reason: str
    ):
        """拒绝订单。"""
        self.order_history.append(Order(
            date=execution_date,
            signal_date=signal_date,
            symbol=symbol,
            side=side,
            target_shares=shares,
            filled_shares=0,
            price=0.0,
            amount=0.0,
            fees=0.0,
            status="rejected",
            reason=reason
        ))

    def record_state(self, date: str, prices: dict[str, float]):
        """记录每日状态。"""
        market_values = {
            symbol: pos.shares * prices.get(symbol, 0)
            for symbol, pos in self.positions.items()
        }

        equity = self.compute_equity(prices)
        self.peak_equity = max(self.peak_equity, equity)
        drawdown = 1 - equity / self.peak_equity if self.peak_equity > 0 else 0

        state = PortfolioState(
            date=date,
            equity=equity,
            cash=self.cash,
            positions=list(self.positions.values()),
            market_values=market_values,
            drawdown=drawdown,
            peak_equity=self.peak_equity
        )

        self.equity_history.append(state)

    def get_summary(self) -> dict:
        """生成汇总统计。"""
        if not self.equity_history:
            return {}

        final_equity = self.equity_history[-1].equity
        total_return = final_equity / self.initial_cash - 1

        daily_returns = []
        for i in range(1, len(self.equity_history)):
            ret = self.equity_history[i].equity / self.equity_history[i-1].equity - 1
            daily_returns.append(ret)

        daily_returns = np.array(daily_returns)

        if len(daily_returns) > 1:
            volatility = float(np.std(daily_returns, ddof=1))
            annual_volatility = volatility * math.sqrt(252)
            sharpe = float(np.mean(daily_returns) / volatility * math.sqrt(252)) if volatility > 1e-12 else None
        else:
            annual_volatility = 0.0
            sharpe = None

        max_drawdown = max((s.drawdown for s in self.equity_history), default=0)

        total_fees = sum(t.fees for t in self.trade_history)
        realized_pnl = sum(t.realized_pnl for t in self.trade_history if t.realized_pnl is not None)

        return {
            "initial_cash": self.initial_cash,
            "final_equity": final_equity,
            "total_return": total_return,
            "annual_return": float((1 + total_return) ** (252 / len(daily_returns)) - 1) if daily_returns.size > 0 else 0,
            "annual_volatility": annual_volatility,
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
            "total_trades": len(self.trade_history),
            "total_orders": len(self.order_history),
            "rejected_orders": sum(1 for o in self.order_history if o.status == "rejected"),
            "total_fees": total_fees,
            "realized_pnl": realized_pnl,
            "evaluation_days": len(daily_returns),
        }
