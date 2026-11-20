"""因子分析模块：IC 时间序列、分组收益、暴露分析、行业中性 Alpha。

对应设计文档阶段三的因子分析需求。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
import numpy as np
from scipy.stats import spearmanr

from .selection import StockCandidate


@dataclass
class RankICResult:
    """Rank IC 计算结果。"""
    signal_date: str
    ic: float
    p_value: float
    sample_size: int
    market_cap_ranks: dict[str, int] = field(default_factory=dict)


@dataclass
class GroupStats:
    """分组统计信息。"""
    group_id: int
    avg_return: float
    cumulative_return: float
    symbols_count: int
    avg_market_cap: float
    symbols: list[str] = field(default_factory=list)


@dataclass
class GroupReturnsResult:
    """五分组收益分析结果。"""
    groups: dict[int, GroupStats] = field(default_factory=dict)
    monotonicity_check: bool = False
    group1_excess_return: float = 0.0


@dataclass
class ExposureResult:
    """因子暴露分析结果。"""
    strategy_industry_weights: dict[str, float] = field(default_factory=dict)
    benchmark_industry_weights: dict[str, float] = field(default_factory=dict)
    industry_overweight: dict[str, float] = field(default_factory=dict)
    avg_market_cap: float = 0.0
    benchmark_avg_market_cap: float = 0.0
    volatility: float = 0.0
    benchmark_volatility: float = 0.0
    avg_adv: float = 0.0
    benchmark_avg_adv: float = 0.0


@dataclass
class AlphaResult:
    """行业中性 Alpha 分解结果。"""
    total_excess_return: float = 0.0
    industry_attribution: float = 0.0
    security_selection_alpha: float = 0.0
    alpha_ratio: float = 0.0


class FactorAnalyzer:
    """因子分析器：计算 IC、分组收益、暴露和 Alpha。"""

    def __init__(self):
        pass

    def compute_rank_ic(
        self,
        signal_date: str,
        candidates: list[StockCandidate],
        returns: dict[str, float]
    ) -> RankICResult:
        """计算 Rank IC（市值因子与收益的秩相关）。

        Args:
            signal_date: 信号日期（月末）
            candidates: 候选股票列表，已按市值升序排列
            returns: 持股期间的收益 {symbol: return}

        Returns:
            RankICResult 包含 IC、p-value、样本数
        """
        # 构建市值排名数组
        market_cap_ranks = {c.symbol: i + 1 for i, c in enumerate(candidates)}

        # 提取有收益数据的股票
        valid_symbols = [s for s in market_cap_ranks.keys() if s in returns]

        if len(valid_symbols) < 3:
            # 样本太少，无法计算 IC
            return RankICResult(
                signal_date=signal_date,
                ic=0.0,
                p_value=1.0,
                sample_size=len(valid_symbols),
                market_cap_ranks=market_cap_ranks
            )

        # 提取排名和收益数组
        ranks = np.array([market_cap_ranks[s] for s in valid_symbols])
        returns_array = np.array([returns[s] for s in valid_symbols])

        # 计算秩相关（Spearman）
        ic, p_value = spearmanr(ranks, returns_array)

        return RankICResult(
            signal_date=signal_date,
            ic=float(ic) if not np.isnan(ic) else 0.0,
            p_value=float(p_value) if not np.isnan(p_value) else 1.0,
            sample_size=len(valid_symbols),
            market_cap_ranks=market_cap_ranks
        )

    def compute_group_returns(
        self,
        candidates: list[StockCandidate],
        returns_by_group: dict[int, dict[str, float]]
    ) -> GroupReturnsResult:
        """计算五分组收益。

        Args:
            candidates: 候选股票列表，已按市值升序排列
            returns_by_group: 按分组的收益数据 {group_id: {symbol: return}}

        Returns:
            GroupReturnsResult 包含 5 组的收益统计
        """
        result = GroupReturnsResult()

        # 如果候选少于 5 只，按实际数量分组
        num_groups = min(5, max(1, len(candidates) // 1))  # 至少 1 组
        if len(candidates) >= 5:
            num_groups = 5
        else:
            num_groups = len(candidates)

        # 平均分组
        group_size = len(candidates) // num_groups
        remainder = len(candidates) % num_groups

        group_returns_dict = {}
        group_symbols_dict = {}

        for group_id in range(1, num_groups + 1):
            # 计算该组的起始和结束索引
            start_idx = (group_id - 1) * group_size + min(group_id - 1, remainder)
            if group_id <= remainder:
                end_idx = start_idx + group_size + 1
            else:
                end_idx = start_idx + group_size

            group_candidates = candidates[start_idx:end_idx]
            group_symbols = [c.symbol for c in group_candidates]
            group_symbols_dict[group_id] = group_symbols

            # 获取该组的收益
            if group_id in returns_by_group:
                group_rets = returns_by_group[group_id]
            else:
                # 如果没有按分组的数据，使用空字典
                group_rets = {}

            # 计算平均收益
            valid_returns = [group_rets.get(s, 0) for s in group_symbols]
            if valid_returns:
                avg_return = np.mean(valid_returns)
                cumulative_return = np.prod([1 + r for r in valid_returns]) - 1
            else:
                avg_return = 0.0
                cumulative_return = 0.0

            # 计算平均市值
            avg_market_cap = np.mean([c.market_cap for c in group_candidates])

            group_returns_dict[group_id] = GroupStats(
                group_id=group_id,
                avg_return=avg_return,
                cumulative_return=cumulative_return,
                symbols_count=len(group_symbols),
                avg_market_cap=avg_market_cap,
                symbols=group_symbols
            )

        result.groups = group_returns_dict

        # 检查单调性：是否 group1 >= group2 >= ... >= group5
        group_avg_returns = [group_returns_dict[i].avg_return for i in range(1, num_groups + 1)]
        is_monotonic = all(
            group_avg_returns[i] >= group_avg_returns[i + 1]
            for i in range(len(group_avg_returns) - 1)
        )
        result.monotonicity_check = is_monotonic

        # 计算第1组 vs 最后一组的超额收益
        if num_groups > 1:
            result.group1_excess_return = (
                group_returns_dict[1].avg_return -
                group_returns_dict[num_groups].avg_return
            )
        else:
            result.group1_excess_return = 0.0

        return result

    def compute_exposure(
        self,
        portfolio_weights: dict[str, float],
        benchmark_weights: dict[str, float],
        symbol_industry: dict[str, str],
        symbol_market_cap: Optional[dict[str, float]] = None,
        symbol_adv: Optional[dict[str, float]] = None
    ) -> ExposureResult:
        """计算因子暴露：行业、波动、流动性。

        Args:
            portfolio_weights: 策略持仓权重 {symbol: weight}
            benchmark_weights: 基准持仓权重 {symbol: weight}
            symbol_industry: 股票行业映射 {symbol: industry_code}
            symbol_market_cap: 股票市值（可选）
            symbol_adv: 股票 ADV20（可选）

        Returns:
            ExposureResult 包含暴露数据
        """
        result = ExposureResult()

        # 计算行业权重
        strategy_industry_weights = {}
        benchmark_industry_weights = {}

        for symbol, weight in portfolio_weights.items():
            industry = symbol_industry.get(symbol, "Unknown")
            strategy_industry_weights[industry] = (
                strategy_industry_weights.get(industry, 0) + weight
            )

        for symbol, weight in benchmark_weights.items():
            industry = symbol_industry.get(symbol, "Unknown")
            benchmark_industry_weights[industry] = (
                benchmark_industry_weights.get(industry, 0) + weight
            )

        result.strategy_industry_weights = strategy_industry_weights
        result.benchmark_industry_weights = benchmark_industry_weights

        # 计算行业超配
        all_industries = set(strategy_industry_weights.keys()) | set(
            benchmark_industry_weights.keys()
        )
        industry_overweight = {}
        for ind in all_industries:
            industry_overweight[ind] = (
                strategy_industry_weights.get(ind, 0) -
                benchmark_industry_weights.get(ind, 0)
            )
        result.industry_overweight = industry_overweight

        # 计算加权平均市值
        if symbol_market_cap:
            strategy_market_cap = sum(
                portfolio_weights.get(s, 0) * symbol_market_cap.get(s, 0)
                for s in set(portfolio_weights.keys()) | set(symbol_market_cap.keys())
            )
            benchmark_market_cap = sum(
                benchmark_weights.get(s, 0) * symbol_market_cap.get(s, 0)
                for s in set(benchmark_weights.keys()) | set(symbol_market_cap.keys())
            )
            result.avg_market_cap = strategy_market_cap
            result.benchmark_avg_market_cap = benchmark_market_cap

        # 计算加权平均 ADV
        if symbol_adv:
            strategy_adv = sum(
                portfolio_weights.get(s, 0) * symbol_adv.get(s, 0)
                for s in set(portfolio_weights.keys()) | set(symbol_adv.keys())
            )
            benchmark_adv = sum(
                benchmark_weights.get(s, 0) * symbol_adv.get(s, 0)
                for s in set(benchmark_weights.keys()) | set(symbol_adv.keys())
            )
            result.avg_adv = strategy_adv
            result.benchmark_avg_adv = benchmark_adv

        return result

    def compute_industry_neutral_alpha(
        self,
        strategy_returns: float,
        benchmark_returns: float,
        industry_weights: dict[str, float],
        industry_excess_returns: dict[str, float]
    ) -> AlphaResult:
        """计算行业中性 Alpha 分解。

        Args:
            strategy_returns: 策略总收益
            benchmark_returns: 基准总收益
            industry_weights: 策略行业权重 {industry: weight}
            industry_excess_returns: 行业超额收益 {industry: excess_return}

        Returns:
            AlphaResult 包含 Alpha 分解结果
        """
        result = AlphaResult()

        # 总超额收益
        total_excess = strategy_returns - benchmark_returns
        result.total_excess_return = total_excess

        # 行业归因 = Σ(行业权重 × 行业超额收益)
        industry_attribution = sum(
            industry_weights.get(ind, 0) * industry_excess_returns.get(ind, 0)
            for ind in set(industry_weights.keys()) | set(industry_excess_returns.keys())
        )
        result.industry_attribution = industry_attribution

        # 选股 Alpha = 总超额 - 行业归因
        security_selection_alpha = total_excess - industry_attribution
        result.security_selection_alpha = security_selection_alpha

        # Alpha 比率
        if abs(total_excess) > 1e-8:
            result.alpha_ratio = security_selection_alpha / total_excess
        else:
            result.alpha_ratio = 0.0

        return result

    def analyze_full(
        self,
        backtest_result: dict,
        market_data: dict[str, pd.DataFrame],
        symbol_industry: dict[str, str]
    ) -> dict:
        """执行完整因子分析。

        Args:
            backtest_result: 回测结果（包含 equity、trades、orders）
            market_data: 市场行情数据 {symbol: quotes_df}
            symbol_industry: 股票行业映射

        Returns:
            完整分析结果字典
        """
        result = {
            "rank_ic_series": [],
            "group_returns": None,
            "exposure": None,
            "alpha": None,
            "summary": {}
        }

        # TODO: 实现完整流程
        # 这个方法在 Task 5 中实现

        return result
