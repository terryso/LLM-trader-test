# DeepSeek Paper Trading Bot 项目总览

> 本文档基于现有代码与 README 反向整理，帮助快速理解项目目标、能力边界与模块划分，便于后续 PRD、架构和实现工作。

## 1. 项目背景与目标

- **项目名称**：LLM-trader-test / DeepSeek Paper Trading Bot
- **项目类型**：多资产加密货币交易机器人 + 可视化仪表盘
- **核心思路**：
  - 使用 **Binance REST API** 拉取多周期 K 线数据（15m / 1h / 4h）。
  - 使用本地指标引擎计算 EMA、RSI、MACD、ATR 等技术指标。
  - 将多周期行情 + 指标 + 仓位状态组织成结构化 prompt，交给 **DeepSeek（通过 OpenRouter）** 决策。
  - 本地执行一套严格的 **风险与资金管理规则**（1–2% 风险上限、强制止损等），决定是否采纳 LLM 建议并进行下单（纸上交易或 Hyperliquid 实盘）。
  - 将组合状态、交易历史、AI 决策和消息日志落地到 `data/` 目录下的 CSV/JSON，并通过 **Streamlit 仪表盘** 展示表现。

该项目主要用于：
- 作为 **学习 / 实验用的 LLM 驱动交易系统样板**。
- 在安全的纸上环境中探索多周期策略 + LLM 决策的可行性。
- 在需要时，将成交同步到 **Hyperliquid 主网** 做小额实盘验证。

## 2. 使用场景与边界

### 2.1 典型用户

- 想快速体验「LLM+技术指标」交易系统的个人量化 / 加密交易爱好者。
- 想研究 LLM 交易决策行为、Prompt 设计和风险约束的工程师或研究者。

### 2.2 场景

- **纸上交易（默认）**：
  - 全部订单与盈亏在本地 CSV/JSON 中模拟，不接触真实资金。
- **Hyperliquid 实盘（可选）**：
  - 当环境变量开启 `HYPERLIQUID_LIVE_TRADING` 且配置钱包与私钥时，
    `hyperliquid_client.py` 会将成交同步到 Hyperliquid 主网，并自动附加止损/止盈订单。
- **回测 / 研究**：
  - 使用 `backtest.py` 在历史数据上重放策略与 LLM 决策，输出完整的回测轨迹，以便分析。
- **可视化 & 监控**：
  - 使用 `dashboard.py` 通过 Streamlit 展示账户净值、收益曲线、Sharpe/Sortino、持仓与交易明细。

### 2.3 非目标

- 本项目 **不会** 提供「保证盈利」或「自动资产管理」服务。
- 不包含端到端风控系统、复杂资金分仓管理、合规模块等企业级要求。
- 不提供任何形式的投资建议，属于 **教育与实验性** 工具。

## 3. 核心特性概览

1. **多时间框架策略**：
   - 4H：大级别趋势与波动（趋势/均线/ATR）。
   - 1H：结构层（摆动高低点、结构突破）。
   - 15m：执行层（精确入场信号，如 RSI14、MACD 交叉等）。
2. **LLM 决策合约**：
   - DeepSeek 必须返回固定 JSON 结构（包含 `signal`、`side`、`quantity`、`profit_target`、`stop_loss`、`confidence` 等）。
   - Bot 在本地校验 JSON 结构与字段合法性，不合规则拒绝执行。
3. **风险与资金管理**：
   - 单笔风险控制在组合资金的 1–2%。
   - 所有交易必须带有预先定义的止损；禁止无止损裸奔。
   - 区分 With-trend / Counter-trend / Range 等不同类型的入场，分配不同风险预算。
4. **可选 Hyperliquid 实盘执行**：
   - 通过 `HyperliquidTradingClient` 把纸上成交同步到主网。
   - 自动根据 tick size 正规化价格，使用 IOC/GTC 等合适的 TIF 策略。
5. **回测与重放**：
   - `backtest.py` 重用线上执行逻辑，在历史数据上跑同一套策略与 LLM Prompt。
   - `replay/` 提供 HTML 回放入口，便于从「故事视角」回顾系统行为。
6. **仪表盘与可视化**：
   - `dashboard.py` 基于 `portfolio_state.csv` 和 `trade_history.csv` 构建多图表 UI。
   - 对比组合表现与「BTC 单币买入持有」基准曲线。

## 4. 技术栈与外部依赖

### 4.1 语言与运行环境

- **语言**：Python 3.x
- **推荐运行方式**：Docker 容器（Linux/AMD64），或本地 Python 环境。

### 4.2 主要 Python 依赖（来自 `requirements.txt`）

- `python-binance`：Binance REST API 客户端
- `pandas` / `numpy`：数据处理与数值计算
- `requests`：HTTP 调用（例如 OpenRouter、其他 REST）
- `python-dotenv`：加载 `.env` 配置
- `colorama`：控制台彩色输出
- `streamlit`：可视化仪表盘
- `hyperliquid-python-sdk`、`eth-account`：Hyperliquid 实盘交易支持

### 4.3 外部服务依赖

- **Binance 现货 / 合约 REST API**：行情与订单信息来源。
- **OpenRouter + DeepSeek**：LLM 决策模型调用。
- **Hyperliquid**：实盘订单路由与撮合（可选）。
- **Telegram Bot API**：通知与交易信号推送（可选）。

## 5. 源码结构与模块职责

### 5.1 顶层文件与目录

- `bot.py`
  - 交易主循环：拉行情 → 算指标 → 组织 prompt → 调用 DeepSeek → 校验决策 → 纸上/实盘执行 → 记录日志。
  - 管理全局组合状态与 CSV/JSON 持久化。
- `backtest.py`
  - 回测驱动器：在历史数据上驱动与线上相同的决策和执行逻辑。
- `dashboard.py`
  - Streamlit 仪表盘：从 `data/` 拉取 CSV，计算 Sortino/Sharpe，并绘制图表。
- `hyperliquid_client.py`
  - Hyperliquid 交易适配器：管理钱包、L2 行情、价格精度与触发单（SL/TP）。
- `data/`
  - 默认数据目录，存放组合状态、交易记录、AI 决策、消息等 CSV/JSON。
- `prompts/`
  - 系统 Prompt 模板，例如 `system_prompt.txt`、`system_prompt_sniper.txt`。
- `scripts/`
  - 辅助脚本：重新计算组合状态、回测 Docker 启动脚本、Hyperliquid smoke test 等。
- `replay/`
  - 回放站点构建脚本与静态页面。
- `docs/`
  - 文档输出目录（本文件与 PRD、架构文档均位于此）。

## 6. 典型运行方式（简要）

### 6.1 运行纸上交易 Bot（Docker）

1. 准备 `.env`，填入：
   - `BN_API_KEY` / `BN_SECRET`
   - `OPENROUTER_API_KEY`
   - 可选：Telegram / Hyperliquid 相关变量
2. 构建镜像：
   - `docker build -t tradebot .`
3. 启动纸上交易：
   - `docker run --rm -it --env-file .env -v "$(pwd)/data:/app/data" tradebot`

### 6.2 启动仪表盘

- `docker run --rm -it --env-file .env -v "$(pwd)/data:/app/data" -p 8501:8501 tradebot streamlit run dashboard.py`

### 6.3 启动回测

- 本地：`python3 backtest.py`
- Docker 辅助脚本：`./scripts/run_backtest_docker.sh <START> <END> <PROMPT_FILE>`

---

后续文档：
- `docs/prd.md`：在此总览基础上，给出更正式的产品需求文档。
- `docs/architecture.md`：从组件与数据流视角进一步拆解系统架构。
