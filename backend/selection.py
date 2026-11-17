"""选股模块：小市值排序、候选集合生成和目标持仓。

对应设计文档第3节：第一版基线V1规则。
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SelectionConfig:
    """选股配置参数。"""
    target_stocks: int = 30  # 目标持股数量
    target_budget: float = 0.9  # 目标股票预算比例
    min_adv20: float = 20_000_000  # 最低20日平均成交额（元）
    min_percentile: float = 0.01  # 市值百分位下限（排除最小1%）
    max_percentile: float = 0.20  # 市值百分位上限（前20%）
    min_listed_days: int = 250  # 最低上市交易日数

    def __post_init__(self):
        """参数验证。"""
        if not 1 <= self.target_stocks <= 100:
            raise ValueError("目标持股数须在1-100之间")
        if not 0.01 <= self.target_budget <= 1.0:
            raise ValueError("目标预算须在0.01-1.0之间")
        if self.min_adv20 < 0:
            raise ValueError("最低ADV20不能为负")
        if not 0 <= self.min_percentile < self.max_percentile <= 1:
            raise ValueError("百分位范围无效")


@dataclass
class StockCandidate:
    """候选股票信息。"""
    symbol: str
    market_cap: float
    adv20: float
    rank: int
    percentile: float
    close: float
    trading_status: str = "trading"
    risk_status: str = "normal"
    listed_days: int = 0


class SmallCapSelector:
    """小市值选股器。

    实现设计文档第3.2节的固定顺序选股逻辑。
    """

    def __init__(self, config: SelectionConfig | None = None):
        self.config = config or SelectionConfig()

    def select(
        self,
        universe: pd.DataFrame,
        market_caps: dict[str, float],
        adv20_values: dict[str, float],
        prices: dict[str, float],
        trading_status: dict[str, str] | None = None,
        risk_status: dict[str, str] | None = None,
        listed_days: dict[str, int] | None = None,
    ) -> tuple[list[StockCandidate], dict]:
        """执行选股流程。

        Args:
            universe: 历史股票池DataFrame，至少包含symbol列
            market_caps: {symbol: market_cap} 总市值字典
            adv20_values: {symbol: adv20} 20日平均成交额字典
            prices: {symbol: close_price} 收盘价字典
            trading_status: {symbol: status} 交易状态，默认全部"trading"
            risk_status: {symbol: status} 风险状态，默认全部"normal"
            listed_days: {symbol: days} 上市交易日数，默认全部满足

        Returns:
            (候选列表, 统计信息)
        """
        trading_status = trading_status or {}
        risk_status = risk_status or {}
        listed_days = listed_days or {}

        stats = {
            "total_universe": len(universe),
            "filtered_basic": 0,
            "filtered_liquidity": 0,
            "filtered_trading": 0,
            "eligible_for_ranking": 0,
            "in_target_percentile": 0,
            "final_selected": 0,
            "insufficient_candidates": False,
        }

        # 步骤1-2：基础资格过滤（ST、退市整理、上市时长）
        eligible = []
        for symbol in universe["symbol"]:
            risk = risk_status.get(symbol, "normal")
            days = listed_days.get(symbol, 999999)

            # 过滤ST、退市整理
            if risk not in {"normal"}:
                continue

            # 过滤上市时长不足
            if days < self.config.min_listed_days:
                continue

            eligible.append(symbol)

        stats["filtered_basic"] = len(eligible)

        # 步骤3：流动性过滤（ADV20、未停牌）
        liquid = []
        for symbol in eligible:
            adv20 = adv20_values.get(symbol, 0)
            status = trading_status.get(symbol, "trading")

            # 检查ADV20
            if adv20 < self.config.min_adv20:
                continue

            # 检查是否停牌
            if status != "trading":
                continue

            liquid.append(symbol)

        stats["filtered_liquidity"] = len(liquid)
        stats["filtered_trading"] = len(liquid)

        # 步骤4-5：读取总市值并排序
        candidates_with_cap = []
        for symbol in liquid:
            cap = market_caps.get(symbol)
            if cap is None or cap <= 0:
                continue
            candidates_with_cap.append((symbol, cap))

        # 按市值升序排序，相同市值按symbol排序（稳定）
        candidates_with_cap.sort(key=lambda x: (x[1], x[0]))

        stats["eligible_for_ranking"] = len(candidates_with_cap)

        if len(candidates_with_cap) == 0:
            return [], stats

        # 步骤5：计算百分位
        N = len(candidates_with_cap)
        ranked = []
        for rank, (symbol, cap) in enumerate(candidates_with_cap, start=1):
            percentile = rank / N
            ranked.append((symbol, cap, rank, percentile))

        # 步骤6：筛选目标百分位范围
        in_range = [
            item for item in ranked
            if self.config.min_percentile < item[3] <= self.config.max_percentile
        ]

        stats["in_target_percentile"] = len(in_range)

        # 步骤6：从中按市值升序选择前N只
        selected_count = min(self.config.target_stocks, len(in_range))
        if selected_count < self.config.target_stocks:
            stats["insufficient_candidates"] = True

        selected = in_range[:selected_count]

        # 构建候选对象
        candidates = []
        for symbol, cap, rank, percentile in selected:
            candidates.append(StockCandidate(
                symbol=symbol,
                market_cap=cap,
                adv20=adv20_values.get(symbol, 0),
                rank=rank,
                percentile=percentile,
                close=prices.get(symbol, 0),
                trading_status=trading_status.get(symbol, "trading"),
                risk_status=risk_status.get(symbol, "normal"),
                listed_days=listed_days.get(symbol, 0),
            ))

        stats["final_selected"] = len(candidates)

        return candidates, stats

    def compute_target_weights(
        self,
        candidates: list[StockCandidate]
    ) -> dict[str, float]:
        """计算目标权重（等权）。

        Args:
            candidates: 候选股票列表

        Returns:
            {symbol: weight} 权重字典
        """
        if not candidates:
            return {}

        # 单名义权重 = 总预算 / 持股数
        weight_per_stock = self.config.target_budget / len(candidates)

        return {c.symbol: weight_per_stock for c in candidates}

    def compute_target_shares(
        self,
        candidates: list[StockCandidate],
        weights: dict[str, float],
        total_equity: float
    ) -> dict[str, int]:
        """计算目标股数（整手）。

        Args:
            candidates: 候选股票列表
            weights: 权重字典
            total_equity: 总资产

        Returns:
            {symbol: shares} 股数字典（100的整数倍）
        """
        shares = {}
        for candidate in candidates:
            weight = weights.get(candidate.symbol, 0)
            target_value = total_equity * weight

            # 按收盘价计算股数，向下取整到100股
            if candidate.close > 0:
                raw_shares = target_value / candidate.close
                shares[candidate.symbol] = int(raw_shares // 100) * 100
            else:
                shares[candidate.symbol] = 0

        return shares
