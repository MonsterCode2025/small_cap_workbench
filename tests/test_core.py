"""测试模块：核心逻辑单元测试。"""
import pytest
from backend.selection import SelectionConfig, SmallCapSelector, StockCandidate
from backend.portfolio import Portfolio, FeeConfig
import pandas as pd


class TestSelection:
    """测试选股模块。"""

    def test_selection_config_validation(self):
        """测试配置验证。"""
        # 正常配置
        config = SelectionConfig(target_stocks=30, target_budget=0.9)
        assert config.target_stocks == 30

        # 异常配置
        with pytest.raises(ValueError):
            SelectionConfig(target_stocks=0)

        with pytest.raises(ValueError):
            SelectionConfig(target_budget=1.5)

    def test_small_cap_selector_basic(self):
        """测试基本选股逻辑。"""
        selector = SmallCapSelector(SelectionConfig(
            target_stocks=3,
            min_adv20=10_000_000,
            min_percentile=0.0,
            max_percentile=1.0,  # 包含全部百分位
            min_listed_days=0  # 测试时关闭上市时长限制
        ))

        # 构造测试数据
        universe = pd.DataFrame({
            "symbol": ["SZ.000001", "SZ.000002", "SZ.000003", "SZ.000004", "SZ.000005"]
        })

        market_caps = {
            "SZ.000001": 1e8,    # 最小，rank=1, percentile=0.2
            "SZ.000002": 2e8,    # rank=2, percentile=0.4
            "SZ.000003": 3e8,    # rank=3, percentile=0.6
            "SZ.000004": 4e8,    # rank=4, percentile=0.8
            "SZ.000005": 5e8,    # rank=5, percentile=1.0
        }

        adv20_values = {s: 15_000_000 for s in universe["symbol"]}
        prices = {s: 10.0 for s in universe["symbol"]}
        listed_days = {s: 300 for s in universe["symbol"]}  # 全部满足上市时长

        candidates, stats = selector.select(
            universe=universe,
            market_caps=market_caps,
            adv20_values=adv20_values,
            prices=prices,
            listed_days=listed_days
        )

        # 应该选出3只最小市值的股票
        assert len(candidates) == 3
        assert candidates[0].symbol == "SZ.000001"
        assert candidates[1].symbol == "SZ.000002"
        assert candidates[2].symbol == "SZ.000003"

        # 验证统计信息
        assert stats["total_universe"] == 5
        assert stats["final_selected"] == 3

    def test_liquidity_filter(self):
        """测试流动性过滤。"""
        selector = SmallCapSelector(SelectionConfig(
            target_stocks=2,
            min_adv20=20_000_000,
            min_listed_days=0,  # 测试时关闭上市时长限制
            min_percentile=0.0,  # 包含所有百分位
            max_percentile=1.0
        ))

        universe = pd.DataFrame({
            "symbol": ["SZ.000001", "SZ.000002", "SZ.000003"]
        })

        market_caps = {s: 1e8 for s in universe["symbol"]}
        adv20_values = {
            "SZ.000001": 25_000_000,  # 满足
            "SZ.000002": 15_000_000,  # 不满足
            "SZ.000003": 30_000_000,  # 满足
        }
        prices = {s: 10.0 for s in universe["symbol"]}
        listed_days = {s: 300 for s in universe["symbol"]}  # 全部满足上市时长

        candidates, stats = selector.select(
            universe=universe,
            market_caps=market_caps,
            adv20_values=adv20_values,
            prices=prices,
            listed_days=listed_days
        )

        # 只有2只满足流动性要求
        assert len(candidates) == 2
        assert "SZ.000002" not in [c.symbol for c in candidates]


class TestPortfolio:
    """测试组合账户模块。"""

    def test_portfolio_initialization(self):
        """测试组合初始化。"""
        portfolio = Portfolio(initial_cash=100_000)
        assert portfolio.cash == 100_000
        assert len(portfolio.positions) == 0

    def test_buy_order_execution(self):
        """测试买入订单执行。"""
        portfolio = Portfolio(initial_cash=100_000, slippage_bps=0)

        target_shares = {"SZ.000001": 1000}
        prices = {"SZ.000001": 10.0}

        portfolio.execute_rebalance(
            signal_date="2024-01-31",
            execution_date="2024-02-01",
            target_shares=target_shares,
            prices=prices
        )

        # 检查持仓
        assert portfolio.get_position_shares("SZ.000001") == 1000
        assert portfolio.cash < 100_000  # 扣除成本和费用

    def test_sell_order_execution(self):
        """测试卖出订单执行。"""
        portfolio = Portfolio(initial_cash=100_000, slippage_bps=0)

        # 先买入
        portfolio.execute_rebalance(
            signal_date="2024-01-31",
            execution_date="2024-02-01",
            target_shares={"SZ.000001": 1000},
            prices={"SZ.000001": 10.0}
        )

        initial_cash = portfolio.cash

        # 再卖出
        portfolio.execute_rebalance(
            signal_date="2024-02-29",
            execution_date="2024-03-01",
            target_shares={"SZ.000001": 0},
            prices={"SZ.000001": 11.0}
        )

        # 检查持仓清空
        assert portfolio.get_position_shares("SZ.000001") == 0
        assert portfolio.cash > initial_cash  # 盈利

    def test_t_plus_1_restriction(self):
        """测试T+1限制。"""
        portfolio = Portfolio(initial_cash=100_000)

        # 买入
        portfolio.execute_rebalance(
            signal_date="2024-01-31",
            execution_date="2024-02-01",
            target_shares={"SZ.000001": 1000},
            prices={"SZ.000001": 10.0}
        )

        # 当天尝试卖出（应该被拒绝）
        portfolio.execute_rebalance(
            signal_date="2024-02-01",
            execution_date="2024-02-01",
            target_shares={"SZ.000001": 0},
            prices={"SZ.000001": 11.0}
        )

        # 持仓应该还在
        assert portfolio.get_position_shares("SZ.000001") == 1000

    def test_insufficient_cash(self):
        """测试资金不足。"""
        portfolio = Portfolio(initial_cash=5000)

        # 尝试买入超出预算的股票
        portfolio.execute_rebalance(
            signal_date="2024-01-31",
            execution_date="2024-02-01",
            target_shares={"SZ.000001": 10000},  # 需要10万元
            prices={"SZ.000001": 10.0}
        )

        # 应该只买入能买得起的部分（整手）
        assert portfolio.get_position_shares("SZ.000001") < 10000


class TestFeeCalculation:
    """测试费用计算。"""

    def test_buy_fees(self):
        """测试买入费用。"""
        fee_config = FeeConfig()
        fees = fee_config.calculate(10000, "buy", "2024-01-01")

        assert fees["commission"] >= 5.0  # 至少最低佣金
        assert fees["stamp"] == 0.0  # 买入无印花税
        assert fees["transfer"] > 0
        assert fees["total"] == fees["commission"] + fees["transfer"]

    def test_sell_fees_after_stamp_tax_cut(self):
        """测试印花税下调后的卖出费用。"""
        fee_config = FeeConfig()

        # 2023-08-28之后：0.05%
        fees_new = fee_config.calculate(10000, "sell", "2024-01-01")
        assert fees_new["stamp"] == 5.0  # 10000 * 0.0005

        # 2023-08-28之前：0.1%
        fees_old = fee_config.calculate(10000, "sell", "2023-01-01")
        assert fees_old["stamp"] == 10.0  # 10000 * 0.001


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
