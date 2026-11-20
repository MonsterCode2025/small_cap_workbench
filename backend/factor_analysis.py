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
            signal_date: 调仓信号日期
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

        equity = backtest_result.get("equity_curve_full", backtest_result.get("equity_curve", backtest_result.get("equity", [])))
        orders = backtest_result.get("orders_full", backtest_result.get("orders", []))
        trades = backtest_result.get("trades_full", backtest_result.get("trades", []))

        if not equity or not orders:
            print(f"[因子分析] 数据不足：equity={len(equity)}, orders={len(orders)}")
            return result

        print(f"[因子分析] 开始分析：equity={len(equity)}, orders={len(orders)}, trades={len(trades)}")

        # 1. 构建调仓日期列表和对应的订单数据
        equity_df = pd.DataFrame(equity)
        equity_df["date"] = pd.to_datetime(equity_df["date"])

        # 从订单中获取有交易意图的信号日期
        signal_dates = {}  # {signal_date: [orders]}
        for order in orders:
            sig_date = order.get("signal_date")
            if sig_date:
                if sig_date not in signal_dates:
                    signal_dates[sig_date] = []
                signal_dates[sig_date].append(order)

        print(f"[因子分析] 找到 {len(signal_dates)} 个有订单的调仓信号日期")

        if not signal_dates:
            return result

        # 2. 对有订单的调仓日期计算 IC，以实际调仓日程确定持有区间。
        sorted_signal_dates = sorted(signal_dates.keys())
        scheduled_dates = sorted(set(backtest_result.get("rebalance_signal_dates", [])) | signal_dates.keys())
        for i, signal_date in enumerate(scheduled_dates):
            if signal_date not in signal_dates:
                continue

            candidates_dict = {}  # {symbol: info}
            for order in signal_dates[signal_date]:
                symbol = order.get("symbol")
                if not symbol or symbol not in market_data:
                    continue

                quotes = market_data[symbol]
                if quotes.empty:
                    continue

                signal_quotes = quotes[quotes["date"] <= signal_date]
                if signal_quotes.empty:
                    continue

                last_row = signal_quotes.iloc[-1]
                # 尝试从 quotes 中获取 market_cap，如果没有则从 close 估算
                market_cap = last_row.get("market_cap")
                if market_cap is None or market_cap == 0:
                    market_cap = last_row.get("close", 10.0) * 1e8  # 简单估算

                candidates_dict[symbol] = {
                    "symbol": symbol,
                    "market_cap": market_cap,
                    "adv20": last_row.get("adv20", 20e6),
                    "close": last_row.get("close", 10.0),
                }

            if not candidates_dict:
                print(f"[因子分析] {signal_date}: 没有有效的候选股票")
                continue

            # 构建候选列表（按市值升序）
            sorted_candidates = sorted(
                candidates_dict.values(), key=lambda x: x["market_cap"]
            )
            candidates = [
                StockCandidate(
                    c["symbol"],
                    c["market_cap"],
                    c["adv20"],
                    rank=j + 1,
                    percentile=(j + 1) / len(sorted_candidates),
                    close=c["close"],
                )
                for j, c in enumerate(sorted_candidates)
            ]

            # 获取后续持股期间的收益
            if i < len(scheduled_dates) - 1:
                next_signal_date = scheduled_dates[i + 1]
                end_date = next_signal_date
            else:
                end_date = equity_df["date"].max().strftime("%Y-%m-%d")

            # 计算持股期间各股票的收益
            returns = {}
            for symbol in candidates_dict.keys():
                if symbol not in market_data:
                    continue

                quotes = market_data[symbol]
                signal_quotes = quotes[quotes["date"] <= signal_date]
                end_quotes = quotes[(quotes["date"] > signal_date) & (quotes["date"] <= end_date)]

                if signal_quotes.empty or end_quotes.empty:
                    continue

                signal_price = signal_quotes.iloc[-1].get("close", 10.0)
                end_price = end_quotes.iloc[-1].get("close", 10.0)

                if signal_price > 0:
                    period_return = (end_price - signal_price) / signal_price
                    returns[symbol] = period_return

            # 计算 IC
            if len(returns) >= 3:
                ic_result = self.compute_rank_ic(signal_date, candidates, returns)
                result["rank_ic_series"].append({
                    "signal_date": ic_result.signal_date,
                    "ic": ic_result.ic,
                    "p_value": ic_result.p_value,
                    "sample_size": ic_result.sample_size,
                })

        print(f"[因子分析] 计算 IC 完成：{len(result['rank_ic_series'])} 个调仓信号")

        # 3. 计算整个回测期的五分组收益
        all_candidates = []

        for signal_date in sorted_signal_dates:
            signal_orders = signal_dates[signal_date]

            for order in signal_orders:
                symbol = order.get("symbol")
                if not symbol or symbol not in market_data:
                    continue

                quotes = market_data[symbol]
                if quotes.empty:
                    continue

                signal_quotes = quotes[quotes["date"] <= signal_date]
                if signal_quotes.empty:
                    continue

                market_cap = signal_quotes.iloc[-1].get("market_cap")
                if market_cap is None or market_cap == 0:
                    market_cap = signal_quotes.iloc[-1].get("close", 10.0) * 1e8

                all_candidates.append({
                    "symbol": symbol,
                    "market_cap": market_cap,
                    "adv20": signal_quotes.iloc[-1].get("adv20", 20e6),
                    "close": signal_quotes.iloc[-1].get("close", 10.0),
                })

        if all_candidates:
            # 按市值升序排列
            sorted_all = sorted(all_candidates, key=lambda x: x["market_cap"])
            candidate_objs = [
                StockCandidate(
                    c["symbol"],
                    c["market_cap"],
                    c["adv20"],
                    rank=j + 1,
                    percentile=(j + 1) / len(sorted_all),
                    close=c["close"],
                )
                for j, c in enumerate(sorted_all)
            ]

            # 收集所有股票的收益
            if sorted_signal_dates:
                last_signal_date = sorted_signal_dates[-1]
                last_returns = {}

                for c in all_candidates:
                    symbol = c["symbol"]
                    if symbol not in market_data:
                        continue

                    quotes = market_data[symbol]
                    signal_quotes = quotes[quotes["date"] <= last_signal_date]

                    if signal_quotes.empty:
                        continue

                    signal_price = signal_quotes.iloc[-1].get("close", 10.0)
                    end_quotes = quotes[quotes["date"] > last_signal_date]

                    if end_quotes.empty or signal_price == 0:
                        continue

                    end_price = end_quotes.iloc[-1].get("close", 10.0)
                    last_returns[symbol] = (end_price - signal_price) / signal_price

                # 构建按分组的收益
                returns_by_group = {}
                if len(candidate_objs) >= 5:
                    group_size = len(candidate_objs) // 5
                    for group_id in range(1, 6):
                        start_idx = (group_id - 1) * group_size
                        end_idx = start_idx + group_size if group_id < 5 else len(candidate_objs)
                        group_symbols = [c.symbol for c in candidate_objs[start_idx:end_idx]]
                        group_returns = {s: last_returns.get(s, 0) for s in group_symbols}
                        returns_by_group[group_id] = group_returns

                if returns_by_group:
                    group_result = self.compute_group_returns(candidate_objs, returns_by_group)
                    result["group_returns"] = {
                        "groups": {
                            gid: {
                                "group_id": gs.group_id,
                                "avg_return": gs.avg_return,
                                "cumulative_return": gs.cumulative_return,
                                "symbols_count": gs.symbols_count,
                                "avg_market_cap": gs.avg_market_cap,
                            }
                            for gid, gs in group_result.groups.items()
                        },
                        "monotonicity_check": group_result.monotonicity_check,
                        "group1_excess_return": group_result.group1_excess_return,
                    }

        # 4. 计算策略 vs 基准的暴露
        # 从 orders/trades 重建最后的持仓（equity_curve 中的 positions 只是数量，不是明细）
        strategy_weights = {}
        strategy_market_cap = {}
        strategy_adv = {}

        if trades and len(trades) > 0:
            # 按股票代码统计买卖数量
            position_shares = {}
            for trade in trades:
                symbol = trade.get("symbol")
                side = trade.get("side")
                shares = trade.get("shares", 0)

                if symbol not in position_shares:
                    position_shares[symbol] = 0

                if side == "buy":
                    position_shares[symbol] += shares
                elif side == "sell":
                    position_shares[symbol] -= shares

            # 只保留有正持仓的股票
            current_positions = {s: sh for s, sh in position_shares.items() if sh > 0}

            if current_positions and equity and len(equity) > 0:
                # 获取最后一个 equity_curve 数据中的总权益
                last_equity_record = equity[-1]
                total_equity = last_equity_record.get("equity", 1)

                # 计算权重和暴露
                for symbol, shares in current_positions.items():
                    if symbol not in market_data:
                        continue

                    quotes = market_data[symbol]
                    if quotes.empty:
                        continue

                    last_close = quotes.iloc[-1].get("close", 10.0)
                    position_value = shares * last_close
                    weight = position_value / total_equity if total_equity > 0 else 0

                    strategy_weights[symbol] = weight
                    strategy_market_cap[symbol] = quotes.iloc[-1].get("market_cap", last_close * 1e8)
                    strategy_adv[symbol] = quotes.iloc[-1].get("adv20", 20e6)

                # 基准权重：全市场等权
                all_symbols_in_data = list(market_data.keys())
                benchmark_weight = 1 / len(all_symbols_in_data) if all_symbols_in_data else 0
                benchmark_weights = {s: benchmark_weight for s in all_symbols_in_data}

                # 计算暴露
                exposure_result = self.compute_exposure(
                    strategy_weights,
                    benchmark_weights,
                    symbol_industry,
                    strategy_market_cap,
                    strategy_adv
                )
                result["exposure"] = {
                    "strategy_industry_weights": exposure_result.strategy_industry_weights,
                    "benchmark_industry_weights": exposure_result.benchmark_industry_weights,
                    "industry_overweight": exposure_result.industry_overweight,
                    "avg_market_cap": exposure_result.avg_market_cap,
                    "benchmark_avg_market_cap": exposure_result.benchmark_avg_market_cap,
                    "avg_adv": exposure_result.avg_adv,
                    "benchmark_avg_adv": exposure_result.benchmark_avg_adv,
                }

        print(f"[因子分析] 完成。IC数={len(result['rank_ic_series'])}, 暴露={result['exposure'] is not None}")
        return result

        if not equity or not orders:
            return result

        # 1. 构建月末调仓日期列表和对应的订单数据
        equity_df = pd.DataFrame(equity)
        equity_df["date"] = pd.to_datetime(equity_df["date"])

        # 从订单中获取所有月末信号日期
        signal_dates = {}  # {signal_date: [orders]}
        for order in orders:
            sig_date = order.get("signal_date")
            if sig_date:
                if sig_date not in signal_dates:
                    signal_dates[sig_date] = []
                signal_dates[sig_date].append(order)

        # 2. 对每个月末调仓日期计算 IC
        sorted_signal_dates = sorted(signal_dates.keys())
        for i, signal_date in enumerate(sorted_signal_dates):
            # 获取该月末调仓的候选股票
            month_orders = signal_dates[signal_date]
            candidates_dict = {}  # {symbol: market_cap}

            for order in month_orders:
                symbol = order.get("symbol")
                # 从市场数据中获取市值（简化：用收盘价 × 假定股数）
                if symbol in market_data:
                    quotes = market_data[symbol]
                    signal_quotes = quotes[quotes["date"] <= signal_date]
                    if not signal_quotes.empty:
                        last_row = signal_quotes.iloc[-1]
                        market_cap = last_row.get("market_cap", 1e8)  # 默认值
                        candidates_dict[symbol] = {
                            "symbol": symbol,
                            "market_cap": market_cap,
                            "adv20": last_row.get("adv20", 20e6),
                            "close": last_row.get("close", 10.0),
                        }

            if not candidates_dict:
                continue

            # 构建候选列表（按市值升序）
            sorted_candidates = sorted(
                candidates_dict.values(), key=lambda x: x["market_cap"]
            )
            candidates = [
                StockCandidate(
                    c["symbol"],
                    c["market_cap"],
                    c["adv20"],
                    rank=j + 1,
                    percentile=(j + 1) / len(sorted_candidates),
                    close=c["close"],
                )
                for j, c in enumerate(sorted_candidates)
            ]

            # 获取后续持股期间的收益
            # 如果是最后一个月末，则到回测结束
            if i < len(sorted_signal_dates) - 1:
                next_signal_date = sorted_signal_dates[i + 1]
                end_date = next_signal_date
            else:
                # 使用最后的 equity 日期
                end_date = equity_df["date"].max().strftime("%Y-%m-%d")

            # 计算持股期间各股票的收益
            returns = {}
            for symbol in candidates_dict.keys():
                if symbol not in market_data:
                    continue

                quotes = market_data[symbol]
                signal_quotes = quotes[quotes["date"] <= signal_date]
                end_quotes = quotes[(quotes["date"] > signal_date) & (quotes["date"] <= end_date)]

                if signal_quotes.empty or end_quotes.empty:
                    continue

                signal_price = signal_quotes.iloc[-1].get("close", 10.0)
                end_price = end_quotes.iloc[-1].get("close", 10.0)

                if signal_price > 0:
                    period_return = (end_price - signal_price) / signal_price
                    returns[symbol] = period_return

            # 计算 IC
            if returns:
                ic_result = self.compute_rank_ic(signal_date, candidates, returns)
                result["rank_ic_series"].append({
                    "signal_date": ic_result.signal_date,
                    "ic": ic_result.ic,
                    "p_value": ic_result.p_value,
                    "sample_size": ic_result.sample_size,
                })

        # 3. 计算整个回测期的五分组收益
        # 收集所有月末调仓的候选股票
        all_candidates = []
        returns_by_group = {}

        for signal_date in sorted_signal_dates:
            month_orders = signal_dates[signal_date]
            month_returns = {}

            for order in month_orders:
                symbol = order.get("symbol")
                if symbol not in market_data:
                    continue

                quotes = market_data[symbol]
                signal_quotes = quotes[quotes["date"] <= signal_date]

                if signal_quotes.empty:
                    continue

                # 简化：所有月末放在一起，不分群
                if symbol not in market_data:
                    continue

                # 获取该股票的市值
                market_cap = signal_quotes.iloc[-1].get("market_cap", 1e8)
                all_candidates.append({
                    "symbol": symbol,
                    "market_cap": market_cap,
                    "adv20": signal_quotes.iloc[-1].get("adv20", 20e6),
                    "close": signal_quotes.iloc[-1].get("close", 10.0),
                })

        if all_candidates:
            # 按市值升序排列
            sorted_all = sorted(all_candidates, key=lambda x: x["market_cap"])
            candidate_objs = [
                StockCandidate(
                    c["symbol"],
                    c["market_cap"],
                    c["adv20"],
                    rank=j + 1,
                    percentile=(j + 1) / len(sorted_all),
                    close=c["close"],
                )
                for j, c in enumerate(sorted_all)
            ]

            # 收集所有股票的收益（简化：只用最后一期）
            if sorted_signal_dates:
                last_signal_date = sorted_signal_dates[-1]
                last_returns = {}

                for c in all_candidates:
                    symbol = c["symbol"]
                    if symbol not in market_data:
                        continue

                    quotes = market_data[symbol]
                    signal_quotes = quotes[quotes["date"] <= last_signal_date]

                    if signal_quotes.empty:
                        continue

                    signal_price = signal_quotes.iloc[-1].get("close", 10.0)
                    end_quotes = quotes[quotes["date"] > last_signal_date]

                    if end_quotes.empty:
                        continue

                    end_price = end_quotes.iloc[-1].get("close", 10.0)

                    if signal_price > 0:
                        last_returns[symbol] = (end_price - signal_price) / signal_price

                # 构建按分组的收益
                if len(candidate_objs) >= 5:
                    group_size = len(candidate_objs) // 5
                    for group_id in range(1, 6):
                        start_idx = (group_id - 1) * group_size
                        end_idx = start_idx + group_size if group_id < 5 else len(candidate_objs)
                        group_symbols = [c.symbol for c in candidate_objs[start_idx:end_idx]]
                        group_returns = {s: last_returns.get(s, 0) for s in group_symbols}
                        returns_by_group[group_id] = group_returns

                group_result = self.compute_group_returns(candidate_objs, returns_by_group)
                result["group_returns"] = {
                    "groups": {
                        gid: {
                            "group_id": gs.group_id,
                            "avg_return": gs.avg_return,
                            "cumulative_return": gs.cumulative_return,
                            "symbols_count": gs.symbols_count,
                            "avg_market_cap": gs.avg_market_cap,
                        }
                        for gid, gs in group_result.groups.items()
                    },
                    "monotonicity_check": group_result.monotonicity_check,
                    "group1_excess_return": group_result.group1_excess_return,
                }

        # 4. 计算策略 vs 基准的暴露
        if equity:
            # 从最后一个 equity 快照获取持仓权重
            last_equity = equity[-1]
            positions = last_equity.get("positions", [])
            equity_value = last_equity.get("equity", 0)

            strategy_weights = {}
            strategy_market_cap = {}
            strategy_adv = {}

            for pos in positions:
                symbol = pos.get("symbol")
                shares = pos.get("shares", 0)

                if symbol in market_data:
                    quotes = market_data[symbol]
                    if not quotes.empty:
                        close = quotes.iloc[-1].get("close", 10.0)
                        market_cap = quotes.iloc[-1].get("market_cap", 1e8)
                        adv = quotes.iloc[-1].get("adv20", 20e6)

                        position_value = shares * close
                        weight = position_value / equity_value if equity_value > 0 else 0

                        strategy_weights[symbol] = weight
                        strategy_market_cap[symbol] = market_cap
                        strategy_adv[symbol] = adv

            # 构建全市场等权基准
            all_symbols = set(strategy_weights.keys()) | set(market_data.keys())
            benchmark_weights = {s: 1.0 / len(all_symbols) for s in all_symbols}

            benchmark_market_cap = {}
            benchmark_adv = {}
            for s in all_symbols:
                if s in market_data:
                    quotes = market_data[s]
                    if not quotes.empty:
                        benchmark_market_cap[s] = quotes.iloc[-1].get("market_cap", 1e8)
                        benchmark_adv[s] = quotes.iloc[-1].get("adv20", 20e6)

            exposure_result = self.compute_exposure(
                strategy_weights,
                benchmark_weights,
                symbol_industry,
                strategy_market_cap,
                strategy_adv,
            )

            result["exposure"] = {
                "strategy_industry_weights": exposure_result.strategy_industry_weights,
                "benchmark_industry_weights": exposure_result.benchmark_industry_weights,
                "industry_overweight": exposure_result.industry_overweight,
                "avg_market_cap": exposure_result.avg_market_cap,
                "benchmark_avg_market_cap": exposure_result.benchmark_avg_market_cap,
                "avg_adv": exposure_result.avg_adv,
                "benchmark_avg_adv": exposure_result.benchmark_avg_adv,
            }

        # 5. 计算 Alpha 分解（简化版）
        if equity:
            first_equity = equity[0].get("equity", 0)
            last_equity_val = equity[-1].get("equity", 0)
            strategy_returns = (last_equity_val - first_equity) / first_equity if first_equity > 0 else 0

            # 基准假设为 0（全市场等权基准）
            benchmark_returns = 0

            # 简化：行业超额收益为 0（未精确计算）
            industry_weights = result.get("exposure", {}).get("strategy_industry_weights", {})
            industry_excess_returns = {ind: 0 for ind in industry_weights.keys()}

            alpha_result = self.compute_industry_neutral_alpha(
                strategy_returns, benchmark_returns, industry_weights, industry_excess_returns
            )

            result["alpha"] = {
                "total_excess_return": alpha_result.total_excess_return,
                "industry_attribution": alpha_result.industry_attribution,
                "security_selection_alpha": alpha_result.security_selection_alpha,
                "alpha_ratio": alpha_result.alpha_ratio,
            }

        # 6. 生成摘要
        result["summary"] = {
            "total_ic": np.mean([ic["ic"] for ic in result["rank_ic_series"]]) if result["rank_ic_series"] else 0,
            "avg_ic_pvalue": np.mean([ic["p_value"] for ic in result["rank_ic_series"]]) if result["rank_ic_series"] else 1.0,
            "ic_count": len(result["rank_ic_series"]),
        }

        return result
