"""因子分析模块测试。"""
import pytest
import pandas as pd
import numpy as np
from backend.factor_analysis import (
    FactorAnalyzer,
    RankICResult,
    GroupReturnsResult,
    ExposureResult,
    AlphaResult,
    GroupStats,
)
from backend.selection import StockCandidate


class TestRankIC:
    """Rank IC 测试。"""

    def test_rank_ic_basic(self):
        """测试 Rank IC 计算的基本逻辑。"""
        analyzer = FactorAnalyzer()

        # 构造测试候选（固定市值排序）
        candidates = [
            StockCandidate("SZ.000001", 1e8, 20e6, rank=1, percentile=0.2, close=10.0),
            StockCandidate("SZ.000002", 2e8, 20e6, rank=2, percentile=0.4, close=10.0),
            StockCandidate("SZ.000003", 3e8, 20e6, rank=3, percentile=0.6, close=10.0),
        ]

        # 构造收益（与市值反向，验证秩相关）
        returns = {
            "SZ.000001": 0.05,  # 最小市值，收益最高
            "SZ.000002": 0.03,
            "SZ.000003": 0.01,  # 最大市值，收益最低
        }

        result = analyzer.compute_rank_ic("2024-02-29", candidates, returns)

        assert isinstance(result, RankICResult)
        assert result.signal_date == "2024-02-29"
        assert result.sample_size == 3
        assert result.ic < -0.5  # 负相关
        assert result.p_value < 1.0  # 有效的 p-value

    def test_rank_ic_with_missing_data(self):
        """测试 Rank IC 计算时缺失收益数据。"""
        analyzer = FactorAnalyzer()

        candidates = [
            StockCandidate("SZ.000001", 1e8, 20e6, rank=1, percentile=0.2, close=10.0),
            StockCandidate("SZ.000002", 2e8, 20e6, rank=2, percentile=0.4, close=10.0),
            StockCandidate("SZ.000003", 3e8, 20e6, rank=3, percentile=0.6, close=10.0),
        ]

        # 只有两个收益数据
        returns = {
            "SZ.000001": 0.05,
            "SZ.000002": 0.03,
            # SZ.000003 缺失
        }

        result = analyzer.compute_rank_ic("2024-02-29", candidates, returns)

        assert result.sample_size == 2
        assert result.ic == 0.0  # 样本太少

    def test_rank_ic_no_returns(self):
        """测试收益数据为空的情况。"""
        analyzer = FactorAnalyzer()

        candidates = [
            StockCandidate("SZ.000001", 1e8, 20e6, rank=1, percentile=0.2, close=10.0),
        ]

        returns = {}

        result = analyzer.compute_rank_ic("2024-02-29", candidates, returns)

        assert result.sample_size == 0
        assert result.ic == 0.0


class TestGroupReturns:
    """五分组收益测试。"""

    def test_group_returns_basic(self):
        """测试五分组收益计算。"""
        analyzer = FactorAnalyzer()

        # 10 只股票，市值升序，应分为 5 组，每组 2 只
        candidates = [
            StockCandidate(
                f"SZ.{str(i).zfill(6)}",
                float(i) * 1e8,
                20e6,
                rank=i + 1,
                percentile=(i + 1) * 0.1,
                close=10.0,
            )
            for i in range(10)
        ]

        # 按分组的收益数据
        returns_by_group = {
            1: {"SZ.000000": 0.05, "SZ.000001": 0.05},  # 组1: 5%
            2: {"SZ.000002": 0.04, "SZ.000003": 0.04},  # 组2: 4%
            3: {"SZ.000004": 0.03, "SZ.000005": 0.03},  # 组3: 3%
            4: {"SZ.000006": 0.02, "SZ.000007": 0.02},  # 组4: 2%
            5: {"SZ.000008": 0.01, "SZ.000009": 0.01},  # 组5: 1%
        }

        result = analyzer.compute_group_returns(candidates, returns_by_group)

        assert isinstance(result, GroupReturnsResult)
        assert len(result.groups) == 5
        assert result.groups[1].avg_return > result.groups[5].avg_return  # 单调性
        assert result.monotonicity_check == True
        assert result.group1_excess_return == pytest.approx(0.04, abs=0.001)

    def test_group_returns_insufficient_candidates(self):
        """测试候选不足 5 组的情况。"""
        analyzer = FactorAnalyzer()

        candidates = [
            StockCandidate("SZ.000001", 1e8, 20e6, rank=1, percentile=0.2, close=10.0),
            StockCandidate("SZ.000002", 2e8, 20e6, rank=2, percentile=0.4, close=10.0),
            StockCandidate("SZ.000003", 3e8, 20e6, rank=3, percentile=0.6, close=10.0),
        ]

        returns_by_group = {
            1: {"SZ.000001": 0.05},
            2: {"SZ.000002": 0.03},
            3: {"SZ.000003": 0.01},
        }

        result = analyzer.compute_group_returns(candidates, returns_by_group)

        assert len(result.groups) == 3


class TestExposure:
    """因子暴露测试。"""

    def test_industry_exposure(self):
        """测试行业暴露分析。"""
        analyzer = FactorAnalyzer()

        # 策略持仓（5 只，都是制造业）
        portfolio_weights = {
            "SZ.000001": 0.2,
            "SZ.000002": 0.2,
            "SZ.000003": 0.2,
            "SZ.000004": 0.2,
            "SZ.000005": 0.2,
        }

        # 基准持仓（10 只，5 只制造业 + 5 只其他）
        benchmark_weights = {
            "SZ.000001": 0.1,
            "SZ.000002": 0.1,
            "SZ.000003": 0.1,
            "SZ.000004": 0.1,
            "SZ.000005": 0.1,  # 制造业
            "SH.600001": 0.1,
            "SH.600002": 0.1,
            "SH.600003": 0.1,
            "SH.600004": 0.1,
            "SH.600005": 0.1,  # 金融业
        }

        symbol_industry = {
            "SZ.000001": "C34",
            "SZ.000002": "C34",
            "SZ.000003": "C34",
            "SZ.000004": "C34",
            "SZ.000005": "C34",  # 制造业代码
            "SH.600001": "J66",
            "SH.600002": "J66",
            "SH.600003": "J66",
            "SH.600004": "J66",
            "SH.600005": "J66",  # 金融业代码
        }

        result = analyzer.compute_exposure(
            portfolio_weights, benchmark_weights, symbol_industry
        )

        assert isinstance(result, ExposureResult)
        # 策略 100% 制造业，基准 50% 制造业，所以超配 50%
        assert result.strategy_industry_weights["C34"] == pytest.approx(1.0)
        assert result.benchmark_industry_weights["C34"] == pytest.approx(0.5)
        assert result.industry_overweight["C34"] == pytest.approx(0.5)

    def test_exposure_with_market_cap_and_adv(self):
        """测试包含市值和流动性的暴露分析。"""
        analyzer = FactorAnalyzer()

        portfolio_weights = {"SZ.000001": 1.0}
        benchmark_weights = {"SZ.000001": 0.5, "SZ.000002": 0.5}

        symbol_industry = {"SZ.000001": "C34", "SZ.000002": "C34"}
        symbol_market_cap = {"SZ.000001": 1e8, "SZ.000002": 2e8}
        symbol_adv = {"SZ.000001": 20e6, "SZ.000002": 30e6}

        result = analyzer.compute_exposure(
            portfolio_weights,
            benchmark_weights,
            symbol_industry,
            symbol_market_cap,
            symbol_adv,
        )

        assert result.avg_market_cap == pytest.approx(1e8)
        assert result.benchmark_avg_market_cap == pytest.approx(1.5e8)
        assert result.avg_adv == pytest.approx(20e6)
        assert result.benchmark_avg_adv == pytest.approx(25e6)


class TestAlpha:
    """行业中性 Alpha 测试。"""

    def test_industry_neutral_alpha(self):
        """测试行业中性 Alpha 计算。"""
        analyzer = FactorAnalyzer()

        # 假设策略总收益 10%，基准 8%，超额收益 2%
        strategy_returns = 0.10
        benchmark_returns = 0.08

        # 策略行业权重（100% 制造业）
        industry_weights = {"C34": 1.0}

        # 制造业超额收益 1%（策略制造业 12% vs 基准制造业 11%）
        industry_excess_returns = {"C34": 0.01}

        result = analyzer.compute_industry_neutral_alpha(
            strategy_returns, benchmark_returns, industry_weights, industry_excess_returns
        )

        assert isinstance(result, AlphaResult)
        # 总超额收益 = 2%
        assert result.total_excess_return == pytest.approx(0.02)

        # 行业贡献 = 1% * 100% = 1%
        assert result.industry_attribution == pytest.approx(0.01)

        # 选股 Alpha = 2% - 1% = 1%
        assert result.security_selection_alpha == pytest.approx(0.01)

        # Alpha ratio = 1% / 2% = 50%
        assert result.alpha_ratio == pytest.approx(0.5)

    def test_alpha_with_zero_excess_return(self):
        """测试无超额收益时的 Alpha 计算。"""
        analyzer = FactorAnalyzer()

        result = analyzer.compute_industry_neutral_alpha(
            0.08, 0.08, {"C34": 1.0}, {"C34": 0.0}
        )

        assert result.total_excess_return == 0.0
        assert result.alpha_ratio == 0.0
