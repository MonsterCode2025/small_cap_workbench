"""数据加载模块：完整版数据准备，支持全市场回测。

加载完整股票池和历史行情数据，用于真实回测。
"""
from __future__ import annotations

import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Literal

from .data import (
    fetch_trading_calendar,
    fetch_stock_list,
    fetch_daily_quotes,
    fetch_market_cap,
    parse_symbol
)


class DataLoader:
    """完整数据加载器：加载全市场股票和历史行情。"""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or Path(__file__).parent.parent / "data" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load_backtest_data(
        self,
        start_date: str,
        end_date: str,
        stock_filter: Literal["all", "mainboard", "sample"] = "all",
        max_symbols: int | None = None,
        use_cache: bool = True
    ) -> dict:
        """加载回测所需的所有数据。

        Args:
            start_date: 开始日期
            end_date: 结束日期
            stock_filter: 股票过滤方式
                - "all": 加载所有股票（沪深A股）
                - "mainboard": 仅主板（SH.6*, SZ.000*, SZ.001*)
                - "sample": 样本模式（用于快速测试）
            max_symbols: 最大股票数量限制，None表示不限制
            use_cache: 是否使用缓存

        Returns:
            {
                'trading_dates': list[str],
                'universe_data': dict[str, pd.DataFrame],
                'market_data': dict[str, pd.DataFrame],
                'summary': dict
            }
        """
        print(f"\n{'='*60}")
        print(f"[数据加载] {start_date} 至 {end_date}")
        print(f"{'='*60}")

        # 1. 加载交易日历
        print("\n  [1/3] 加载交易日历...")
        calendar_cache = self.cache_dir / f"calendar_{start_date}_{end_date}.csv"

        if use_cache and calendar_cache.exists():
            calendar = pd.read_csv(calendar_cache)
            calendar["trade_date"] = pd.to_datetime(calendar["trade_date"])
            print(f"    ✓ 从缓存加载")
        else:
            calendar = fetch_trading_calendar(start_date, end_date)
            calendar.to_csv(calendar_cache, index=False)
            print(f"    ✓ 从数据源获取")

        trading_dates = calendar["trade_date"].dt.strftime("%Y-%m-%d").tolist()
        print(f"    ✓ 共 {len(trading_dates)} 个交易日")

        # 2. 加载股票列表
        print(f"\n  [2/3] 加载股票池（模式: {stock_filter}）...")
        stock_list_cache = self.cache_dir / "stock_list.csv"

        if use_cache and stock_list_cache.exists():
            stock_list = pd.read_csv(stock_list_cache)
            print(f"    ✓ 从缓存加载")
        else:
            stock_list = fetch_stock_list()
            stock_list.to_csv(stock_list_cache, index=False)
            print(f"    ✓ 从数据源获取")

        # 根据过滤模式筛选股票
        selected_stocks = self._filter_stocks(stock_list, stock_filter, max_symbols)

        symbols = selected_stocks["symbol"].tolist()
        print(f"    ✓ 筛选后: {len(symbols)} 只股票")

        # 3. 加载行情数据
        print(f"\n  [3/3] 加载行情数据（共 {len(symbols)} 只股票）...")
        market_data = {}
        failed_symbols = []
        success_count = 0

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
                    success_count += 1
                    # 每10只股票报告一次进度
                    if i % 10 == 0 or i == len(symbols):
                        print(f"    进度: {i}/{len(symbols)} ({success_count} 成功, {len(failed_symbols)} 失败)")
                else:
                    failed_symbols.append((symbol, "无数据"))

            except Exception as e:
                failed_symbols.append((symbol, str(e)))

        # 过滤失败的股票
        successful_symbols = [s for s in symbols if s not in [fs[0] for fs in failed_symbols]]

        # 4. 构建universe_data（每日股票池）
        universe_df = pd.DataFrame({
            "symbol": successful_symbols,
            "name": [selected_stocks[selected_stocks["symbol"] == s]["name"].values[0]
                     for s in successful_symbols]
        })

        # 简化：所有交易日使用相同的股票池
        # TODO: 未来版本可以根据上市日期动态构建每日股票池
        universe_data = {date: universe_df.copy() for date in trading_dates}

        print(f"\n{'='*60}")
        print(f"[数据加载完成]")
        print(f"  交易日: {len(trading_dates)} 天")
        print(f"  股票数: {len(successful_symbols)} 只")
        print(f"  失败数: {len(failed_symbols)} 只")
        print(f"  成功率: {len(successful_symbols)/len(symbols)*100:.1f}%")
        print(f"  行情记录: {sum(len(df) for df in market_data.values())} 条")
        print(f"{'='*60}\n")

        return {
            "trading_dates": trading_dates,
            "universe_data": universe_data,
            "market_data": market_data,
            "summary": {
                "start_date": start_date,
                "end_date": end_date,
                "total_trading_days": len(trading_dates),
                "requested_symbols": len(symbols),
                "successful_symbols": len(successful_symbols),
                "failed_symbols": len(failed_symbols),
                "success_rate": len(successful_symbols) / len(symbols) if symbols else 0,
                "total_records": sum(len(df) for df in market_data.values()),
                "stock_filter": stock_filter,
                "symbols": successful_symbols[:50]  # 只保存前50个用于显示
            }
        }

    def _filter_stocks(
        self,
        stock_list: pd.DataFrame,
        filter_mode: Literal["all", "mainboard", "sample"],
        max_symbols: int | None
    ) -> pd.DataFrame:
        """根据模式过滤股票。

        Args:
            stock_list: 完整股票列表
            filter_mode: 过滤模式
            max_symbols: 最大数量限制

        Returns:
            过滤后的股票列表
        """
        if filter_mode == "all":
            # 加载所有股票
            selected = stock_list.copy()

        elif filter_mode == "mainboard":
            # 仅主板股票：SH.6*, SZ.000*, SZ.001*
            selected = stock_list[
                stock_list["symbol"].str.match(r"^(SH\.6|SZ\.000|SZ\.001)")
            ].copy()

        elif filter_mode == "sample":
            # 样本模式：取部分主板股票用于测试
            sz_stocks = stock_list[stock_list["symbol"].str.startswith("SZ.000")].head(10)
            sh_stocks = stock_list[stock_list["symbol"].str.startswith("SH.600")].head(10)
            selected = pd.concat([sz_stocks, sh_stocks], ignore_index=True)

        else:
            raise ValueError(f"不支持的过滤模式: {filter_mode}")

        # 应用最大数量限制
        if max_symbols is not None and len(selected) > max_symbols:
            selected = selected.head(max_symbols)

        return selected


def prepare_sample_data(months: int = 3) -> dict:
    """准备样本数据（用于快速测试）。

    Args:
        months: 回测月数（1-6个月）

    Returns:
        回测数据字典
    """
    from datetime import datetime, timedelta

    end_date = datetime.now()
    start_date = end_date - timedelta(days=months * 30)

    loader = DataLoader()
    return loader.load_backtest_data(
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        stock_filter="sample",
        use_cache=True
    )
