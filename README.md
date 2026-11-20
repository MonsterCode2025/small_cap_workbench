# 小市值策略研究工作台

## 项目概述

这是一个基于**可验证、可迭代**理念的小市值量化策略研究系统，严格遵循[设计文档](D:\lgl\code\quant\docs\superpowers\specs\2026-11-04-small-cap-iterative-strategy-design.md)中的研发方法。

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
│   ├── data.py              # 数据获取、交易日历、股票池
│   ├── data_loader.py       # 完整版数据加载器
│   ├── data_audit.py        # 数据审计模块
│   ├── period_manager.py    # 区间管理模块
│   ├── selection.py         # 选股逻辑、排序、过滤
│   ├── portfolio.py         # 多股票账户、调仓执行、费用
│   ├── backtest.py          # 回测引擎、历史模拟
│   └── app.py               # FastAPI服务
├── frontend/
│   └── index.html           # Web界面
├── tests/
│   └── test_core.py         # 核心逻辑测试
├── docs/
│   ├── 模块详解.md           # 详细模块文档
│   ├── 新增功能使用说明.md   # 功能使用指南
│   └── 更新总结.md           # 更新记录
├── data/                    # 数据快照（gitignore）
├── outputs/                 # 实验结果（gitignore）
├── pyproject.toml           # 依赖配置
├── start.py                 # 启动脚本
└── README.md
```

## 模块概览

| 模块 | 文件 | 状态 | 功能 |
|------|------|------|------|
| **数据模块** | `backend/data.py` | ✅ 完成 | 交易日历、股票池、行情、市值数据获取 |
| **数据加载** | `backend/data_loader.py` | ✅ 完成 | 完整版数据加载，支持全市场 |
| **数据审计** | `backend/data_audit.py` | ✅ 完成 | 验证数据完整性和可靠性 |
| **区间管理** | `backend/period_manager.py` | ✅ 完成 | 管理研究/验证/封存区间 |
| **选股模块** | `backend/selection.py` | ✅ 完成 | 小市值排序、过滤、权重分配 |
| **账户模块** | `backend/portfolio.py` | ✅ 完成 | 多股票持仓、调仓、费用计算 |
| **回测模块** | `backend/backtest.py` | ✅ 完成 | 历史模拟、集成调度 |
| **因子分析** | `backend/factor_analysis.py` | ✅ 完成 | Rank IC、分组收益、暴露、Alpha 分解 |
| **报告生成** | `backend/reports.py` | ✅ 完成 | JSON 和 HTML 报告输出 |
| **API模块** | `backend/app.py` | ✅ 完成 | FastAPI服务、实验管理、因子分析端点 |
| **测试模块** | `tests/test_core.py` | ✅ 完成 | 单元测试覆盖 |

**详细文档**：参见 [模块详解.md](docs/模块详解.md)

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
│  data_loader.py │  数据加载
│  - 批量获取      │  输入: start_date, end_date, stock_filter
│  - 缓存管理      │  输出: trading_dates, universe_data, market_data
│  - 进度显示      │  模式: all/mainboard/sample
└────────┬────────┘
         │
         ├──→ ┌─────────────────┐
         │    │  data_audit.py  │  数据审计
         │    │  - 交易日历审计  │  验证数据完整性
         │    │  - 股票池审计    │  检查覆盖度
         │    │  - 数据可用性    │  抽样检查
         │    └─────────────────┘
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
│  - 审计接口     │  集成审计和区间管理
└─────────────────┘

┌─────────────────┐
│period_manager.py│  区间管理（独立模块）
│  - 定义区间     │  管理研究/验证/封存区间
│  - 锁定机制     │  防止误用封存数据
│  - 配置持久化   │  保存到 data/periods.json
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

#### 运行回测（完整版）

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
    "slippage_bps": 5.0,
    "stock_filter": "mainboard",
    "max_symbols": null
  }'
```

**参数说明**：
- `stock_filter`: 股票过滤方式
  - `"all"`: 全市场（沪深A股）
  - `"mainboard"`: 仅主板（推荐）
  - `"sample"`: 样本测试（20只股票）
- `max_symbols`: 最大股票数限制，`null` 表示不限制

#### 运行数据审计

```bash
curl "http://127.0.0.1:8001/api/audit?start_date=2023-01-01&end_date=2024-12-31"
```

审计内容：
- 交易日历完整性
- 股票池覆盖度
- 市场数据可用性（抽样检查）

#### 查看区间配置

```bash
curl http://127.0.0.1:8001/api/periods
```

#### 锁定历史回测区间

```bash
curl -X POST "http://127.0.0.1:8001/api/periods/lock?period_name=research_2020_2022"
```

## 开发思路

### 阶段一：数据契约（当前）

**目标**：确认历史数据可用性，建立可信回测基础

- [x] 定义数据契约（证券池、市值、状态、事件）
- [x] 实现选股逻辑（市值排序、过滤、整手）
- [x] 实现多股票账户（调仓、费用、T+1）
- [x] 单元测试（选股、组合、费用）
- [x] 数据审计功能（检查数据完整性）
- [x] 区间管理功能（锁定历史回测区间）
- [x] 完整版数据加载（支持全市场）

### 阶段二：基线回测

**目标**：在真实约束下验证V1基线

- [x] 加载历史股票池和市值数据
- [x] 实现月末选股和次日执行
- [x] 处理停牌、涨跌停、订单拒绝
- [x] 生成完整equity/trades/orders记录
- [ ] 压力测试（不同资金、滑点、执行延迟）

### 阶段三：因子分析

**目标**：理解规模信号特征

- [x] Rank IC时间序列
- [x] 五分组收益与单调性
- [x] 行业、波动、流动性暴露
- [x] 控制行业后的增量关系
- [x] API端点和报告生成

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

**阶段一～三：核心系统建设**
- 核心模块实现（data, selection, portfolio, backtest）
- 单元测试覆盖（选股、账户、费用、因子分析）
- API框架（FastAPI后端 + 因子分析端点）
- 配置验证与参数检查
- **数据审计模块**（验证数据完整性）
- **区间管理模块**（管理研究/验证/封存区间）
- **完整版数据加载**（支持全市场回测）

**阶段三：因子分析与报告生成** ✨
- **因子分析模块** v1.1（Rank IC、分组收益、暴露、Alpha分解）
- **报告生成** v1.1（JSON + HTML 报告）
- **POST /api/factor-analysis** 端点（完整因子分析工作流）
- **详细模块文档** [因子分析说明](docs/因子分析说明.md)

### 🚧 进行中

- 前端可视化增强

### 📋 待完成

- 压力测试（不同参数组合）
- 策略增强迭代（V1.1, V1.2, V2等）
- 前向模拟测试

---

## 新增功能总结

### 阶段二：完整版回测系统（v1.0.0）

#### 1. 完整版回测系统

去掉简化版限制，支持：
- **全市场模式** (`stock_filter="all"`)：加载所有沪深A股
- **主板模式** (`stock_filter="mainboard"`)：仅主板股票（推荐）
- **样本模式** (`stock_filter="sample"`)：20只股票快速测试
- **灵活限制** (`max_symbols`)：可选的股票数量上限

#### 2. 数据审计功能

验证数据质量，包括：
- 交易日历完整性（≥200天）
- 股票池覆盖度（≥1000只）
- 市场数据可用性（≥70%成功率）

**使用**：`GET /api/audit?start_date=xxx&end_date=xxx`

#### 3. 区间管理功能

管理历史回测区间，避免过拟合：
- **研究区间** (research)：用于策略开发和调参
- **验证区间** (validation)：独立验证策略效果
- **封存区间** (reserved)：样本外测试（慎用）

**功能**：
- 定义和锁定区间
- 验证回测请求是否在允许的区间内
- 配置持久化到 `data/periods.json`

**使用**：
- `GET /api/periods`：查看所有区间
- `POST /api/periods/lock?period_name=xxx`：锁定区间

---

### 阶段三：因子分析与报告生成（v1.1）

#### 1. 因子分析模块

通过四个核心维度评估策略表现和超额收益来源：

**A. Rank IC 时间序列**
- 计算市值因子与后续持股期间收益的秩相关系数
- 输出：IC值、p-value、T-Stat、样本数
- 衡量因子预测能力的稳定性

**B. 五分组收益分析**
- 按市值升序将候选股票分成5组
- 对比各组的平均收益和累计收益
- 验证小市值溢价是否存在（单调性检验）

**C. 因子暴露分析**
- **行业权重超配**：策略 vs 基准的行业配置差异
- **市值暴露**：策略平均市值 vs 基准平均市值
- **流动性暴露**：策略平均ADV20 vs 基准平均ADV20

**D. 行业中性 Alpha 分解**
- 公式：总超额收益 = 行业配置贡献 + 选股Alpha
- 定量化策略的真实选股能力（剔除行业配置效应）
- Alpha比率：选股Alpha占总超额收益的比例

**API端点**：`POST /api/factor-analysis`
```bash
curl -X POST http://127.0.0.1:8001/api/factor-analysis \
  -H "Content-Type: application/json" \
  -d '{
    "experiment_id": "5e3b2a1c-9f4d-41e2-8b7c-3d5e9f2a1b4c",
    "include_html_report": true
  }'
```

#### 2. 报告生成

自动生成两种格式的报告：

**JSON报告** (`outputs/{experiment_id}/factor_analysis.json`)
- 完整的分析数据结构
- 便于后续处理和二次分析
- 包含IC序列、分组收益、暴露、Alpha分解

**HTML报告** (`outputs/{experiment_id}/factor_report.html`)
- 交互式可视化报告
- 包含IC曲线图、收益对比柱图、行业热力图、Alpha分解饼图
- 支持浏览器打开查看

#### 3. 完整工作流

```
步骤1: 运行回测
  curl -X POST /api/backtest → 获取 experiment_id

步骤2: 运行因子分析
  curl -X POST /api/factor-analysis → 生成分析结果和报告

步骤3: 查看报告
  outputs/{experiment_id}/factor_report.html
```

---

## 相关文档

- [新增功能使用说明](docs/新增功能使用说明.md) - API示例、工作流程、常见问题
- [模块详解](docs/模块详解.md) - 详细的模块接口和实现说明
- [因子分析说明](docs/因子分析说明.md) - 因子分析四大维度的深度解读

---

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
- [新增功能使用说明](docs/新增功能使用说明.md) - API示例和工作流程
- [模块详解](docs/模块详解.md) - 详细的模块接口文档（包含阶段三因子分析模块）
- [因子分析说明](docs/因子分析说明.md) - 因子分析四大维度的深度指南

## 许可

本项目为研究用途，不得用于商业交易。

---

**当前版本**: 1.1.0 - 因子分析版  
**更新日期**: 2026-11-20  
**状态**: 阶段一～三完成。包含完整版回测系统、数据审计、区间管理、因子分析与报告生成
