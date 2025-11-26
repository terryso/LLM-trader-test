## 2. 组件视图

### 2.1 交易主循环（bot.py）

职责：

- 加载 `.env` 与环境变量，解析 API Key、LLM 模型配置、风险参数等。
- 初始化 Binance Client 与 HyperliquidTradingClient（可选）。
- 管理全局组合状态与 CSV 文件（`portfolio_state.csv`、`trade_history.csv` 等）。
- 按固定时间间隔执行交易循环：
  1. 拉取多周期行情。
  2. 计算技术指标。
  3. 组织 LLM Prompt 与上下文。
  4. 调用 DeepSeek 模型获取 JSON 决策。
  5. 校验与约束决策（风控）。
  6. 执行纸上撮合或委托 Hyperliquid 下单。
  7. 更新状态并写入 CSV/JSON。

主要内部子模块（从代码功能角度划分）：

- **配置模块**：
  - 环境变量解析（布尔/整数/浮点/Thinking 参数解析）。
  - 加载系统 Prompt 与 LLM 参数。
- **行情与指标模块**：
  - 使用 Binance API 拉取指定 Symbol 的多周期 K 线。
  - 使用 `pandas` / `numpy` 计算 EMA、RSI、MACD、ATR 等。
- **LLM 决策模块**：
  - 构造包含多时间框架行情 + 仓位 + 风险约束的 prompt。
  - 调用 OpenRouter/DeepSeek，并解析 JSON 决策。
- **执行与风控模块**：
  - 校验 JSON 字段与取值范围。
  - 依据风险规则决定下单规模与 SL/TP。
  - 在纸上/实盘路径之间切换。
- **日志与持久化模块**：
  - 初始化 / 迁移 CSV 列结构。
  - 按迭代写入 portfolio、trades、decisions、messages。

### 2.2 Hyperliquid 执行适配器（hyperliquid_client.py）

职责：

- 在用户显式开启 `HYPERLIQUID_LIVE_TRADING` 且配置钱包与私钥时：
  - 初始化 Hyperliquid Info/Exchange 客户端与本地钱包对象。
  - 校验钱包地址与私钥的对应关系（不一致时给出警告）。
- 提供统一封装：
  - `place_entry_with_sl_tp(...)`：
    - 按合约 tick size 规范化价格，设置杠杆与 TIF（IOC/GTC）。
    - 提交入场订单，若成交则自动挂 SL/TP 触发单。
  - `close_position(...)`：
    - 基于当前持仓或指定 size 提交 reduce-only IOC 平仓单。
- 内部辅助能力：
  - Tick size 发现（优先从合约 meta，其次从 L2 订单簿推导）。
  - 价格正规化与四舍五入规则。

架构位置：

- 作为 `bot.py` 的下游执行适配层，对 `bot` 暴露相对稳定的 Python 接口，屏蔽 Hyperliquid SDK 细节。

### 2.3 回测引擎（backtest.py）

职责：

- 配置回测时间段、K 线周期、LLM 参数与初始资金（基于 `BACKTEST_*` 环境变量）。
- 使用 Binance API 下载所需时间窗口内的历史 K 线数据，并缓存到 `data-backtest/cache/`。
- 构建 `HistoricalBinanceClient`：
  - 对 `bot` 来说看起来像真实 Binance Client，但底层从缓存 DataFrame 取数据。
- 调用 `bot` 模块，重用同样的：
  - 指标计算
  - LLM 决策
  - 交易执行与日志写入逻辑（但写入的是 `data-backtest/run-*/`）。
- 收集回测结果并写入 `backtest_results.json` 等汇总文件。

架构要点：

- 通过 **依赖注入（替换 Binance Client 与数据目录）** 达到「逻辑复用」，避免复制交易逻辑。
- 回测输出布局与线上 `data/` 相似，使得仪表盘可指向回测目录进行分析。

### 2.4 仪表盘（dashboard.py）

职责：

- 加载 `.env`，获取 `BN_API_KEY` / `BN_SECRET`（可选），以便在界面中展示实时价格对比。
- 读取：
  - `portfolio_state.csv`
  - `trade_history.csv`
  - `ai_decisions.csv`
  - `ai_messages.csv`
- 计算：
  - 实现盈亏与未实现盈亏。
  - Sharpe 与 Sortino 比率（按组合净值轨迹计算，考虑风险自由率）。
- 渲染：
  - 账户余额与净值、回报率、Sharpe/Sortino 等关键指标卡片。
  - 净值 vs BTC Buy&Hold 曲线对比图（使用 Altair）。
  - 当前持仓与基于实时价格的未实现盈亏。
  - 交易与 AI 决策表格。

### 2.5 回放与工具（replay/ 与 scripts/）

- **replay/**：
  - `build_replay_site.py` + `index.html`：将历史 CSV/JSON 转化为可交互或静态页面回放，提供「故事化」视角。
- **scripts/**：
  - `recalculate_portfolio.py`：从交易历史重放组合，修正 `portfolio_state`。
  - `manual_hyperliquid_smoke.py`：在 Live 模式前进行小额实盘连通性测试。
  - `run_backtest_docker.sh`：封装 Docker 运行逻辑，方便并行回测。
