# 小市值策略研究工作台

## 项目概述

这是一个基于**可验证、可迭代**理念的小市值量化策略研究系统，严格遵循[设计文档](../../../docs/superpowers/specs/2026-11-04-small-cap-iterative-strategy-design.md)中的研发方法。

### 核心特点

- **数据先行**：历史证券池、时点市值、风险状态的完整契约
- **可追溯决策**：每个调仓日的候选集合、排除原因、目标与实际持仓
- **真实约束**：整手、T+1、涨跌停、停牌、费用、流动性限制
- **独立验证**：研究/验证/封存区间分离，避免过拟合
- **版本管理**：冻结基线V1，增强版本单变量迭代

## 策略逻辑

### V1基线方案

**目标**：建立小市值暴露的可交易基线，作为后续增强的对照

| 维度 | 配置 |
|------|------|
| 市场 | 沪深普通主板A股 |
| 调仓频率 | 月末（最后交易日收盘后生成信号，次日执行）|
| 目标持股 | 30只，等权，90%股票预算 |
| 选股逻辑 | 总市值升序排序，选取1%-20%百分位中最小的30只 |
| 过滤条件 | 非ST、上市≥250日、ADV20≥2000万、未停牌 |
| 执行约束 | 整手、T+1、涨跌停、开盘滑点、3日调仓窗口 |

### 选股流程（固定顺序）

```
1. 还原t日历史证券集合
2. 基础资格过滤（ST、退市整理、上市时长）
3. 流动性过滤（ADV20、停牌）
4. 读取总市值并排序
5. 计算百分位，筛选1%-20%范围
6. 按市值升序选择前30只
7. 生成等权目标，按收盘价计算股数（整手）
```

## 项目结构

```
small_cap_workbench/
├── backend/
│   ├── __init__.py
│   ├── data.py           # 数据获取、交易日历、股票池
│   ├── selection.py      # 选股逻辑、排序、过滤
│   ├── portfolio.py      # 多股票账户、调仓执行、费用
│   ├── backtest.py       # 回测引擎、历史模拟
│   └── app.py            # FastAPI服务
├── tests/
│   └── test_core.py      # 核心逻辑测试
├── data/                 # 数据快照（gitignore）
├── outputs/              # 实验结果（gitignore）
├── pyproject.toml        # 依赖配置
├── start.py              # 启动脚本
└── README.md
```

## 已开发模块详解

### 模块总览

| 模块 | 文件 | 状态 | 功能 |
|------|------|------|------|
| **数据模块** | `backend/data.py` | ✅ 完成 | 交易日历、股票池、行情、市值数据获取 |
| **选股模块** | `backend/selection.py` | ✅ 完成 | 小市值排序、过滤、权重分配 |
| **账户模块** | `backend/portfolio.py` | ✅ 完成 | 多股票持仓、调仓、费用计算 |
| **回测模块** | `backend/backtest.py` | ✅ 完成 | 历史模拟、集成调度 |
| **API模块** | `backend/app.py` | ✅ 完成 | FastAPI服务、实验管理 |
| **测试模块** | `tests/test_core.py` | ✅ 完成 | 单元测试覆盖 |

---

### 1️⃣ 数据模块 (`backend/data.py`)

**功能**：提供历史数据获取、交易日历、股票池构建等基础数据服务

#### 核心函数

##### `fetch_trading_calendar(start, end)`
**功能**：获取交易日历

**输入**：
- `start`: str - 起始日期 "YYYY-MM-DD"
- `end`: str - 结束日期 "YYYY-MM-DD"

**输出**：
- DataFrame，列：`trade_date`

**用途**：识别月末交易日、确定调仓日

---

##### `fetch_stock_list(date=None)`
**功能**：获取沪深A股列表

**输入**：
- `date`: str | None - 指定日期（None表示当前）

**输出**：
- DataFrame，列：`symbol`, `name`, `exchange`, `list_date`

**用途**：构建历史股票池

---

##### `fetch_daily_quotes(symbol, start, end)`
**功能**：获取日线行情（未复权）

**输入**：
- `symbol`: str - 标准格式股票代码（如"SZ.000001"）
- `start`: str - 起始日期
- `end`: str - 结束日期

**输出**：
- DataFrame，列：`date`, `open`, `high`, `low`, `close`, `volume`, `amount`

**用途**：获取收盘价、开盘价、成交额

---

##### `calculate_adv20(quotes, target_date)`
**功能**：计算20日平均成交额（ADV20）

**输入**：
- `quotes`: DataFrame - 日线行情数据
- `target_date`: str - 目标日期

**输出**：
- float - ADV20值（元），数据不足返回0

**用途**：流动性过滤

**算法**：
```python
# 获取目标日期之前的20个交易日
before = quotes[quotes["date"] <= target_date].tail(20)
# 停牌日成交额视为0
adv20 = before["amount"].fillna(0).mean()
```

---

##### `fetch_market_cap(symbol, date)`
**功能**：获取指定日期的总市值

**输入**：
- `symbol`: str - 股票代码
- `date`: str - 日期

**输出**：
- float | None - 总市值（元），失败返回None

**用途**：市值排序

---

##### `UniverseBuilder` 类
**功能**：历史股票池构建器

**方法**：

- `get_month_ends(start, end)` → list[str]
  - 获取区间内的月末交易日列表

- `filter_basic_eligibility(stock_info, date)` → DataFrame
  - 基础资格过滤（当前为框架，待实现ST/退市过滤）

---

### 2️⃣ 选股模块 (`backend/selection.py`)

**功能**：实现小市值选股逻辑，包括过滤、排序、权重分配

#### 核心类

##### `SelectionConfig` (配置类)
**功能**：选股参数配置

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `target_stocks` | int | 30 | 目标持股数量 |
| `target_budget` | float | 0.9 | 目标股票预算比例（90%） |
| `min_adv20` | float | 20,000,000 | 最低20日平均成交额（元） |
| `min_percentile` | float | 0.01 | 市值百分位下限（排除最小1%） |
| `max_percentile` | float | 0.20 | 市值百分位上限（前20%） |
| `min_listed_days` | int | 250 | 最低上市交易日数 |

**验证**：
- `target_stocks`: 1-100
- `target_budget`: 0.01-1.0
- `min_percentile < max_percentile`

---

##### `StockCandidate` (数据类)
**功能**：候选股票信息

**字段**：
- `symbol`: str - 股票代码
- `market_cap`: float - 总市值
- `adv20`: float - 20日平均成交额
- `rank`: int - 市值排名（1=最小）
- `percentile`: float - 百分位（0-1）
- `close`: float - 收盘价
- `trading_status`: str - 交易状态（"trading"/"suspended"）
- `risk_status`: str - 风险状态（"normal"/"st"/"delisted"）
- `listed_days`: int - 上市交易日数

---

##### `SmallCapSelector` 类
**功能**：小市值选股器

**方法 1**: `select()`

**功能**：执行完整选股流程

**输入**：
- `universe`: DataFrame - 历史股票池，必须包含`symbol`列
- `market_caps`: dict[str, float] - 总市值字典
- `adv20_values`: dict[str, float] - ADV20字典
- `prices`: dict[str, float] - 收盘价字典
- `trading_status`: dict[str, str] | None - 交易状态（默认全部"trading"）
- `risk_status`: dict[str, str] | None - 风险状态（默认全部"normal"）
- `listed_days`: dict[str, int] | None - 上市交易日数（默认全部满足）

**输出**：
- `candidates`: list[StockCandidate] - 候选股票列表
- `stats`: dict - 统计信息

**统计信息字段**：
```python
{
    "total_universe": 5000,           # 股票池总数
    "filtered_basic": 4500,           # 基础过滤后
    "filtered_liquidity": 3000,       # 流动性过滤后
    "filtered_trading": 3000,         # 交易状态过滤后
    "eligible_for_ranking": 3000,     # 可排序数量
    "in_target_percentile": 600,      # 目标百分位内
    "final_selected": 30,             # 最终选中
    "insufficient_candidates": False  # 候选不足标记
}
```

**执行流程**：
1. 基础资格过滤（ST、上市时长）
2. 流动性过滤（ADV20、停牌）
3. 市值排序（升序）
4. 计算百分位
5. 筛选1%-20%范围
6. 选择前30只

---

**方法 2**: `compute_target_weights(candidates)`

**功能**：计算目标权重（等权）

**输入**：
- `candidates`: list[StockCandidate]

**输出**：
- dict[str, float] - {symbol: weight}

**算法**：
```python
weight_per_stock = target_budget / len(candidates)  # 0.9 / 30 = 0.03
```

---

**方法 3**: `compute_target_shares(candidates, weights, total_equity)`

**功能**：计算目标股数（整手约束）

**输入**：
- `candidates`: list[StockCandidate]
- `weights`: dict[str, float] - 权重字典
- `total_equity`: float - 总资产

**输出**：
- dict[str, int] - {symbol: shares}，100的整数倍

**算法**：
```python
target_value = total_equity * weight  # 1,000,000 * 0.03 = 30,000
raw_shares = target_value / close     # 30,000 / 10 = 3,000
shares = int(raw_shares // 100) * 100 # 2,900（整手）
```

---

### 3️⃣ 账户模块 (`backend/portfolio.py`)

**功能**：多股票持仓管理、调仓执行、费用计算、T+1限制

#### 核心类

##### `FeeConfig` (配置类)
**功能**：费用配置

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `commission_rate` | float | 0.0003 | 佣金费率（万三） |
| `min_commission` | float | 5.0 | 最低佣金（元） |
| `stamp_tax_rate` | float | 0.0005 | 印花税率（2023-08-28起） |
| `transfer_fee_rate` | float | 0.00001 | 过户费率 |

**方法**: `calculate(amount, side, date)`

**输入**：
- `amount`: float - 成交金额
- `side`: Literal["buy", "sell"] - 买卖方向
- `date`: str - 交易日期

**输出**：
```python
{
    "commission": 15.0,    # 佣金
    "stamp": 50.0,         # 印花税（仅卖出）
    "transfer": 1.0,       # 过户费
    "total": 66.0          # 总费用
}
```

**算法**：
```python
# 佣金：买卖双向
commission = max(5.0, amount * 0.0003)

# 印花税：仅卖出，税率按日期
if side == "sell":
    stamp = amount * (0.0005 if date >= "2023-08-28" else 0.001)

# 过户费：买卖双向
transfer = amount * 0.00001
```

---

##### `Position` (数据类)
**功能**：持仓信息

**字段**：
- `symbol`: str - 股票代码
- `shares`: int - 持仓股数
- `cost_basis`: float - 成本基础（含买入费用）
- `last_buy_date`: str - 最后买入日期（T+1检查）

---

##### `Order` (数据类)
**功能**：订单记录

**字段**：
- `date`: str - 执行日期
- `signal_date`: str - 信号日期
- `symbol`: str
- `side`: Literal["buy", "sell"]
- `target_shares`: int - 目标股数
- `filled_shares`: int - 实际成交股数
- `price`: float - 成交价格
- `amount`: float - 成交金额
- `fees`: float - 费用
- `status`: Literal["filled", "rejected", "partial"]
- `reason`: str - 说明

---

##### `Trade` (数据类)
**功能**：成交记录

**字段**：
- `date`: str
- `symbol`: str
- `side`: Literal["buy", "sell"]
- `shares`: int
- `price`: float
- `amount`: float
- `fees`: float
- `realized_pnl`: float | None - 实现盈亏（仅卖出）

---

##### `PortfolioState` (数据类)
**功能**：组合状态快照

**字段**：
- `date`: str
- `equity`: float - 总资产
- `cash`: float - 现金
- `positions`: list[Position] - 持仓列表
- `market_values`: dict[str, float] - 各股票市值
- `drawdown`: float - 回撤
- `peak_equity`: float - 峰值权益

---

##### `Portfolio` 类
**功能**：多股票组合账户

**初始化参数**：
- `initial_cash`: float - 初始资金
- `fee_config`: FeeConfig | None - 费用配置
- `slippage_bps`: float - 滑点（基点，默认5.0）

**属性**：
- `cash`: float - 当前现金
- `positions`: dict[str, Position] - 持仓字典
- `equity_history`: list[PortfolioState] - 权益历史
- `trade_history`: list[Trade] - 成交历史
- `order_history`: list[Order] - 订单历史

---

**方法 1**: `execute_rebalance()`

**功能**：执行调仓（先卖后买）

**输入**：
- `signal_date`: str - 信号生成日期
- `execution_date`: str - 执行日期
- `target_shares`: dict[str, int] - 目标持仓
- `prices`: dict[str, float] - 开盘价
- `limits`: dict[str, tuple[float, float]] | None - 涨跌停价
- `trading_status`: dict[str, str] | None - 交易状态

**输出**：
```python
{
    "orders": 15,         # 订单总数
    "filled": 12,         # 成交数量
    "rejected": 3,        # 拒绝数量
    "buy_amount": 900000, # 买入金额
    "sell_amount": 50000  # 卖出金额
}
```

**执行逻辑**：
1. **卖出阶段**：清理不在目标中的持仓
2. **买入阶段**：建立新持仓

**检查项**（卖出）：
- 开盘价是否存在
- 是否跌停
- 是否停牌
- T+1限制（当日买入不能卖出）

**检查项**（买入）：
- 开盘价是否存在
- 是否涨停
- 是否停牌
- 资金是否充足
- 整手约束（100的倍数）

---

**方法 2**: `compute_equity(prices)`

**功能**：计算当前总资产

**输入**：
- `prices`: dict[str, float] - 当前价格

**输出**：
- float - 总资产（现金+持仓市值）

---

**方法 3**: `record_state(date, prices)`

**功能**：记录每日状态快照

**输入**：
- `date`: str - 日期
- `prices`: dict[str, float] - 收盘价

**输出**：无（追加到`equity_history`）

---

**方法 4**: `get_summary()`

**功能**：生成汇总统计

**输出**：
```python
{
    "initial_cash": 1000000,
    "final_equity": 1150000,
    "total_return": 0.15,           # 15%
    "annual_return": 0.12,          # 年化收益
    "annual_volatility": 0.18,      # 年化波动率
    "sharpe": 0.67,                 # 夏普比率
    "max_drawdown": 0.08,           # 最大回撤
    "total_trades": 360,            # 成交笔数
    "total_orders": 400,            # 订单总数
    "rejected_orders": 40,          # 拒绝订单
    "total_fees": 5000,             # 总费用
    "realized_pnl": 120000,         # 已实现盈亏
    "evaluation_days": 250          # 评估天数
}
```

---

### 4️⃣ 回测模块 (`backend/backtest.py`)

**功能**：集成选股、账户管理和历史模拟

#### 核心类

##### `BacktestEngine` 类

**初始化参数**：
- `selection_config`: SelectionConfig | None
- `fee_config`: FeeConfig | None
- `initial_cash`: float - 默认1,000,000
- `slippage_bps`: float - 默认5.0

**属性**：
- `selector`: SmallCapSelector - 选股器
- `portfolio`: Portfolio - 账户
- `selection_config`: SelectionConfig - 选股配置

---

**方法**: `run()`

**功能**：执行完整回测

**输入**：
- `trading_dates`: list[str] - 交易日列表
- `universe_data`: dict[str, pd.DataFrame] - 每日股票池 {date: universe_df}
- `market_data`: dict[str, dict[str, pd.DataFrame]] - 市场行情 {symbol: quotes_df}
- `start_date`: str - 开始日期
- `end_date`: str - 结束日期

**输出**：
```python
{
    "summary": {...},          # 汇总统计（见Portfolio.get_summary）
    "equity": [...],           # 权益曲线记录
    "trades": [...],           # 成交记录
    "orders": [...],           # 订单记录
    "config": {...}            # 配置信息
}
```

**权益记录格式**：
```python
{
    "date": "2024-01-05",
    "equity": 1050000,
    "cash": 100000,
    "drawdown": 0.02,
    "positions": 30
}
```

**成交记录格式**：
```python
{
    "date": "2024-01-05",
    "symbol": "SZ.000001",
    "side": "buy",
    "shares": 900,
    "price": 10.05,
    "amount": 9045.0,
    "fees": 5.0,
    "realized_pnl": None
}
```

**订单记录格式**：
```python
{
    "date": "2024-01-05",
    "signal_date": "2024-01-04",
    "symbol": "SZ.000001",
    "side": "buy",
    "target_shares": 1000,
    "filled_shares": 900,
    "status": "partial",
    "reason": "预算限制，仅买入900/1000股"
}
```

**执行流程**：
1. 获取月末日期列表
2. 按交易日循环
3. 月末：生成选股信号、计算目标持仓
4. 次日：执行调仓
5. 每日：记录状态快照
6. 汇总统计

---

### 5️⃣ API模块 (`backend/app.py`)

**功能**：FastAPI服务，提供HTTP接口

#### API端点

##### `GET /api/health`
**功能**：健康检查

**输出**：
```json
{
    "status": "ok",
    "strategy": "small_cap_v1",
    "mode": "research",
    "timestamp": "2024-11-20T10:30:00+08:00"
}
```

---

##### `POST /api/backtest`
**功能**：运行回测

**请求体**：
```json
{
    "start_date": "2023-01-01",
    "end_date": "2024-12-31",
    "initial_cash": 1000000,
    "target_stocks": 30,
    "target_budget": 0.9,
    "min_adv20": 20000000,
    "slippage_bps": 5.0,
    "commission_rate": 0.0003
}
```

**参数验证**：
- `initial_cash`: 100,000 - 10,000,000
- `target_stocks`: 5 - 100
- `target_budget`: 0.1 - 1.0
- `slippage_bps`: 0 - 50

**响应**：
```json
{
    "experiment_id": "uuid",
    "status": "data_not_ready",
    "message": "第一工作包：数据审计阶段...",
    "created_at": "2024-11-20T10:30:00+08:00",
    "config": {...},
    "summary": {...}
}
```

**当前状态**：返回模拟结果结构，等待数据审计通过

---

##### `GET /api/experiments`
**功能**：列出历史实验（最近50个）

**输出**：
```json
{
    "experiments": [
        {
            "experiment_id": "uuid",
            "created_at": "2024-11-20T10:30:00+08:00",
            "summary": {...},
            "config": {...}
        }
    ]
}
```

---

##### `GET /api/experiments/{experiment_id}`
**功能**：获取实验详情

**输出**：完整的实验结果JSON

---

### 6️⃣ 测试模块 (`tests/test_core.py`)

**功能**：核心逻辑单元测试

#### 测试类

##### `TestSelection` - 选股模块测试
- `test_selection_config_validation()` - 配置验证
- `test_small_cap_selector_basic()` - 基本选股逻辑
- `test_liquidity_filter()` - 流动性过滤
- `test_percentile_ranking()` - 百分位筛选

##### `TestPortfolio` - 账户模块测试
- `test_buy_order_execution()` - 买入订单执行
- `test_sell_order_execution()` - 卖出订单执行
- `test_t_plus_1_restriction()` - T+1限制
- `test_insufficient_cash()` - 资金不足处理

##### `TestFees` - 费用模块测试
- `test_buy_fees()` - 买入费用计算
- `test_sell_fees_after_stamp_tax_cut()` - 卖出费用（印花税减半后）

**运行测试**：
```bash
uv run pytest tests/test_core.py -v
```

---

## 模块间数据流

```
┌─────────────────┐
│  data.py        │  获取原始数据
│  - 交易日历      │
│  - 股票池       │
│  - 日线行情      │
│  - ADV20        │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  selection.py   │  选股逻辑
│  - 过滤         │  输入: universe, market_caps, adv20, prices
│  - 排序         │  输出: candidates (30只), stats
│  - 权重分配     │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  portfolio.py   │  账户管理
│  - 调仓执行     │  输入: target_shares, prices
│  - 费用计算     │  输出: 成交记录, 订单记录, 持仓快照
│  - T+1检查      │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  backtest.py    │  回测引擎
│  - 历史模拟     │  输入: trading_dates, universe_data, market_data
│  - 集成调度     │  输出: summary, equity, trades, orders
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  app.py         │  API服务
│  - HTTP接口     │  输入: BacktestRequest
│  - 实验管理     │  输出: JSON结果, 保存到outputs/
└─────────────────┘
```

## 快速开始

### 1. 安装依赖

项目使用uv管理依赖：

```bash
cd strategy/small_cap/small_cap_workbench
uv pip install -e .
```

### 2. 运行测试

验证核心逻辑：

```bash
uv run pytest tests/test_core.py -v
```

### 3. 启动服务

```bash
uv run python start.py
```

服务将在 `http://127.0.0.1:8001` 启动。

### 4. API接口

#### 健康检查

```bash
curl http://127.0.0.1:8001/api/health
```

#### 运行回测（当前为数据审计阶段）

```bash
curl -X POST http://127.0.0.1:8001/api/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2023-01-01",
    "end_date": "2024-12-31",
    "initial_cash": 1000000,
    "target_stocks": 30,
    "target_budget": 0.9,
    "min_adv20": 20000000,
    "slippage_bps": 5.0
  }'
```

## 开发思路

### 阶段一：数据契约（当前）

**目标**：确认历史数据可用性，建立可信回测基础

- [x] 定义数据契约（证券池、市值、状态、事件）
- [x] 实现选股逻辑（市值排序、过滤、整手）
- [x] 实现多股票账户（调仓、费用、T+1）
- [x] 单元测试（选股、组合、费用）
- [ ] 数据审计通过
- [ ] 锁定历史回测区间

### 阶段二：基线回测

**目标**：在真实约束下验证V1基线

- [ ] 加载历史股票池和市值数据
- [ ] 实现月末选股和次日执行
- [ ] 处理停牌、涨跌停、订单拒绝
- [ ] 生成完整equity/trades/orders记录
- [ ] 压力测试（不同资金、滑点、执行延迟）

### 阶段三：因子分析

**目标**：理解规模信号特征

- [ ] Rank IC时间序列
- [ ] 五分组收益与单调性
- [ ] 行业、波动、流动性暴露
- [ ] 控制行业后的增量关系

### 阶段四：增强迭代

**目标**：单变量改进，独立验证

- [ ] V1.1 换手缓冲
- [ ] V1.2 流动性增强
- [ ] V2 质量过滤
- [ ] V3 风险约束
- [ ] V4 择时模块

### 阶段五：前向模拟

**目标**：真实时钟运行

- [ ] 日度数据采集
- [ ] 月末信号生成
- [ ] 对账与异常监控
- [ ] 至少6个完整月度周期

## 核心设计原则

### 1. 时间一致性

- 决策只用t时点已知信息
- 禁止使用未来ST、未来退市提前排除
- 公司行动按可知时间处理

### 2. 执行真实性

- 整手约束，不能买入零股
- T+1限制，买入当日不能卖出
- 涨跌停、停牌保守拒绝
- 现金不足时缩减买入，不借钱

### 3. 费用完整性

- 佣金、印花税、过户费分别计算
- 印花税按历史时点税率（2023-08-28前后）
- 滑点独立于内置成交价

### 4. 归因清晰性

- 规模贡献 vs 选股Alpha
- 行业暴露报告
- 成本与执行分解
- 个股/时期贡献分析

## 测试策略

### 单元测试

```python
# 测试选股逻辑
def test_small_cap_selector_basic()
def test_liquidity_filter()
def test_percentile_ranking()

# 测试账户逻辑
def test_buy_order_execution()
def test_sell_order_execution()
def test_t_plus_1_restriction()
def test_insufficient_cash()

# 测试费用计算
def test_buy_fees()
def test_sell_fees_after_stamp_tax_cut()
```

### 集成测试

- [ ] 完整12个月回测
- [ ] 公司行动处理（分红、送转）
- [ ] 极端情况（全部停牌、大盘跌停）
- [ ] 数据缺失处理

## 关键测试用例

### 1. 月末信号生成

```python
# 在2024-02-29收盘后生成信号
# 最早在2024-03-01开盘执行
assert signal_date == "2024-02-29"
assert execution_date == "2024-03-01"
```

### 2. 卖出受阻

```python
# 股票跌停，卖出拒绝
# 持仓保留，现金未到账
assert portfolio.get_position_shares(symbol) == original_shares
assert portfolio.cash == original_cash
```

### 3. 整手约束

```python
# 预算只够买950股
# 实际买入900股（9手）
assert filled_shares == 900
assert filled_shares % 100 == 0
```

## 配置说明

### SelectionConfig

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `target_stocks` | 30 | 目标持股数量 |
| `target_budget` | 0.9 | 股票预算比例（剩余10%为现金缓冲）|
| `min_adv20` | 20,000,000 | 最低20日平均成交额（元）|
| `min_percentile` | 0.01 | 市值百分位下限（排除最小1%）|
| `max_percentile` | 0.20 | 市值百分位上限 |
| `min_listed_days` | 250 | 最低上市交易日数 |

### FeeConfig

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `commission_rate` | 0.0003 | 佣金费率（万三）|
| `min_commission` | 5.0 | 最低佣金（元）|
| `stamp_tax_rate` | 0.0005 | 印花税率（2023-08-28起）|
| `transfer_fee_rate` | 0.00001 | 过户费率 |

### Portfolio

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `initial_cash` | 1,000,000 | 初始资金（元）|
| `slippage_bps` | 5.0 | 滑点（基点）|

## 当前状态

### ✅ 已完成

- 核心模块实现（data, selection, portfolio, backtest）
- 单元测试覆盖（选股、账户、费用）
- API框架（FastAPI后端）
- 配置验证与参数检查

### 🚧 进行中

- 数据审计（历史股票池、市值、状态）
- 历史覆盖验证

### 📋 待完成

- 完整历史数据加载
- 基线回测运行
- 因子分析报告
- 前端可视化界面

## 注意事项

### 研究模式声明

⚠️ **本工具处于研究阶段，不提供实盘交易建议**

- 历史回测存在选择偏差
- 成本模型为研究假设，非真实冲击
- 样本外被使用后不再是未见数据
- 小市值策略存在流动性、波动、拥挤风险

### 数据质量

当前第一工作包阶段，重点是数据审计：

1. 历史证券池完整性
2. 时点市值可用性
3. 风险状态（ST、退市）准确性
4. 公司行动（分红、送转）覆盖

**不满足数据契约时，明确标记不可回测，不静默降级**

### 风险控制

设计中的风控阈值（10%复核、15%暂停）仅为讨论值：

- 不代表策略一定在阈值止损
- 历史净值不会事后截断
- 真实资金预算需用户确认

## 参考文档

- [小市值策略设计文档](../../../docs/superpowers/specs/2026-11-04-small-cap-iterative-strategy-design.md)
- [量化策略研发步骤2-6](../../../docs/量化策略研发_步骤2至6方法与模型.md)
- [小市值工作台用户说明](../../../docs/小市值工作台用户说明.md)

## 许可

本项目为研究用途，不得用于商业交易。

---

**当前版本**: 1.0.0 - 第一工作包：数据审计与核心逻辑  
**更新日期**: 2024-11-20  
**状态**: 数据契约阶段，等待历史数据审计通过
