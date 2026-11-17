"""数据加载模块：简化版数据准备，用于快速验证回测流程。

当前为演示版本，使用少量股票和短周期数据快速验证整个流程。
完整版需要等待数据审计通过后实现。
"""
from __future__ import annotations

import pandas as pd
from datetime import datetime
from pathlib import Path

from .data import (
    fetch_trading_calendar,
    fetch_stock_list,
    fetch_daily_quotes,
    fetch_market_cap,
    parse_symbol
)


class QuickDataLoader:
    """快速数据加载器：用于验证回测流程。

    使用少量股票（10-20只）和短周期（3-6个月）数据。
    """

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or Path(__file__).parent.parent / "data" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load_backtest_data(
        self,
        start_date: str,
        end_date: str,
        max_symbols: int = 20,
        use_cache: bool = True
    ) -> dict:
        """加载回测所需的所有数据。

        Args:
            start_date: 开始日期
            end_date: 结束日期
            max_symbols: 最多加载股票数（演示版限制）
            use_cache: 是否使用缓存

        Returns:
            {
                'trading_dates': list[str],
                'universe_data': dict[str, pd.DataFrame],
                'market_data': dict[str, pd.DataFrame]
            }
        """
        print(f"[数据加载] 开始加载 {start_date} 至 {end_date} 的数据...")

        # 1. 加载交易日历
        print("  [1/3] 加载交易日历...")
        calendar_cache = self.cache_dir / f"calendar_{start_date}_{end_date}.csv"

        if use_cache and calendar_cache.exists():
            calendar = pd.read_csv(calendar_cache)
            calendar["trade_date"] = pd.to_datetime(calendar["trade_date"])
        else:
            calendar = fetch_trading_calendar(start_date, end_date)
            calendar.to_csv(calendar_cache, index=False)

        trading_dates = calendar["trade_date"].dt.strftime("%Y-%m-%d").tolist()
        print(f"    ✓ 获取 {len(trading_dates)} 个交易日")

        # 2. 加载股票列表（简化版：只取主板头部股票）
        print(f"  [2/3] 加载股票池（最多{max_symbols}只）...")
        stock_list_cache = self.cache_dir / "stock_list.csv"

        if use_cache and stock_list_cache.exists():
            stock_list = pd.read_csv(stock_list_cache)
        else:
            stock_list = fetch_stock_list()
            stock_list.to_csv(stock_list_cache, index=False)

        # 筛选：只取深圳主板（000开头）和上海主板（600开头）
        sz_stocks = stock_list[stock_list["symbol"].str.startswith("SZ.000")].head(max_symbols // 2)
        sh_stocks = stock_list[stock_list["symbol"].str.startswith("SH.600")].head(max_symbols // 2)
        selected_stocks = pd.concat([sz_stocks, sh_stocks], ignore_index=True)

        symbols = selected_stocks["symbol"].tolist()
        print(f"    ✓ 选择 {len(symbols)} 只股票: {symbols[:5]}...")

        # 3. 加载行情数据
        print(f"  [3/3] 加载行情数据...")
        market_data = {}
        failed_symbols = []

        for i, symbol in enumerate(symbols, 1):
            cache_file = self.cache_dir / f"quotes_{symbol}_{start_date}_{end_date}.csv"

            try:
                if use_cache and cache_file.exists():
                    quotes = pd.read_csv(cache_file)
                    quotes["date"] = pd.to_datetime(quotes["date"])
                else:
                    quotes = fetch_daily_quotes(symbol, start_date, end_date)
                    if not quotes.empty:
                        quotes.to_csv(cache_file, index=False)

                if not quotes.empty:
                    market_data[symbol] = quotes
                    print(f"    [{i}/{len(symbols)}] ✓ {symbol}: {len(quotes)} 条记录")
                else:
                    failed_symbols.append(symbol)
                    print(f"    [{i}/{len(symbols)}] ✗ {symbol}: 无数据")

            except Exception as e:
                failed_symbols.append(symbol)
                print(f"    [{i}/{len(symbols)}] ✗ {symbol}: {e}")

        # 过滤失败的股票
        successful_symbols = [s for s in symbols if s not in failed_symbols]

        # 4. 构建universe_data（每日股票池）
        universe_df = pd.DataFrame({
            "symbol": successful_symbols,
            "name": [selected_stocks[selected_stocks["symbol"] == s]["name"].values[0]
                     for s in successful_symbols]
        })

        # 简化：所有交易日使用相同的股票池
        universe_data = {date: universe_df for date in trading_dates}

        print(f"\n[数据加载完成]")
        print(f"  交易日: {len(trading_dates)} 天")
        print(f"  股票数: {len(successful_symbols)} 只 (失败 {len(failed_symbols)} 只)")
        print(f"  行情数据: {sum(len(df) for df in market_data.values())} 条记录")

        return {
            "trading_dates": trading_dates,
            "universe_data": universe_data,
            "market_data": market_data,
            "summary": {
                "total_trading_days": len(trading_dates),
                "total_symbols": len(successful_symbols),
                "failed_symbols": failed_symbols,
                "successful_symbols": successful_symbols
            }
        }


def prepare_demo_data(months: int = 3) -> dict:
    """准备演示数据（3个月，10只股票）。

    Args:
        months: 回测月数（1-6个月）

    Returns:
        回测数据字典
    """
    from datetime import datetime, timedelta

    end_date = datetime.now()
    start_date = end_date - timedelta(days=months * 30)

    loader = QuickDataLoader()
    return loader.load_backtest_data(
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        max_symbols=10,
        use_cache=True
    )
