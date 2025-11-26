## 7. 实现模式与一致性规则（Implementation Patterns）

本节给出 AI/人类开发者在扩展本项目时应遵守的实现模式与约定，用于减少「不同代理各写一套风格」带来的冲突。

---

### 7.1 命名规范（Naming Patterns）

- **Python 模块与脚本**：
  - 使用 `snake_case.py`，顶层入口脚本保持现有命名：`bot.py`、`backtest.py`、`dashboard.py`。
- **函数 / 变量 / 常量**：
  - 遵循 PEP 8：函数与变量使用 `snake_case`，常量使用 `UPPER_SNAKE_CASE`。
- **CSV/JSON 字段**：
  - 字段名统一使用英文 `snake_case`，例如：`total_equity`、`trade_history`、`ai_decisions`。
  - 新增字段时禁止与已有字段重名或含义相悖，应在架构或数据文档中补充说明。
- **目录命名**：
  - 运行时数据目录：`data/`、`data-backtest/`，不再新增平行目录；如需子目录，请在架构文档中说明用途。

> 说明：本项目当前不使用数据库或 HTTP API，因此表名 / REST 路径等命名约定视为 N/A，由未来演进时再补充。

---

### 7.2 目录与代码结构（Structure Patterns）

- **顶层结构**：
  - `bot.py`：唯一的交易主循环入口，不引入第二个「主循环脚本」。
  - `backtest.py`：统一的回测入口，复用 `bot.py` 的指标与执行逻辑。
  - `dashboard.py`：只读取 `data/` 下数据，不写入业务数据。
  - `hyperliquid_client.py`：所有 Hyperliquid 相关逻辑的唯一适配层，不直接在 `bot.py` 中使用 SDK。
- **扩展策略 / 工具代码**：
  - 推荐新增 Python 模块放在顶层或 `scripts/` 下，避免在 `bot.py` 内堆积过多无关逻辑。
  - 如需提取通用工具，可引入 `utils_*.py` 风格的模块，并在架构文档中补充说明用途。
- **测试目录（推荐模式）**：
  - 若引入自动化测试，统一放在 `tests/` 目录中，结构镜像源代码：
    - `tests/test_bot_core.py`
    - `tests/test_backtest_harness.py`
  - 使用 pytest 风格的 `test_*.py` 文件。

---

### 7.3 数据与格式模式（Format Patterns）

- **时间与时区**：
  - 所有持久化时间戳（CSV / JSON）使用 `ISO 8601` 字符串（`datetime.isoformat()`），统一为 **UTC**。
- **CSV 文件规范**：
  - 关键文件：
    - `portfolio_state.csv`：权益曲线与持仓快照；列集由 `STATE_COLUMNS` 常量约束。
    - `trade_history.csv`：交易记录（ENTRY / CLOSE）。
    - `ai_decisions.csv`：简化版 AI 决策摘要（含 `signal` 与 `confidence`）。
    - `ai_messages.csv`：完整 Prompt 与模型回复日志。
  - 修改或新增列时，应同步更新：
    - `bot.py` 中 CSV 初始化与读取逻辑；
    - 架构文档的数据说明。
- **LLM 决策 JSON 模式**：
  - Bot 期待的基础字段包括：`signal`、`side`、`quantity`、`profit_target`、`stop_loss`、`leverage`、`confidence`、`risk_usd` 等。
  - 新增字段需保持向后兼容：在解析逻辑中设默认值，并在文档中说明含义与取值范围。

---

### 7.4 通信与耦合模式（Communication Patterns）

- **子系统间通信**：
  - 执行 / 回测 → 通过写入 `data/` 与 `data-backtest/` 进行解耦。
  - 仪表盘 / 回放 → 只读上述目录，不直接调用 `bot.py` 逻辑。
- **外部服务集成**：
  - Binance / Hyperliquid / LLM / Telegram 等外部调用统一通过专门函数封装，不在业务逻辑中随意散落裸请求。
  - 新增外部服务时，优先创建单独适配模块或函数，保持调用点集中便于替换。

---

### 7.5 生命周期与错误处理模式（Lifecycle & Error Handling）

- **交易循环生命周期**：
  1. 加载/刷新配置与环境变量。
  2. 拉取多时间框架行情并计算指标。
  3. 根据仓位与风险参数构建 Prompt，调用 LLM。
  4. 校验 JSON 决策的结构与约束（包括风险上限与字段范围）。
  5. 在纸上/实盘路径中执行交易。
  6. 更新状态与 CSV/JSON，记录日志与 Telegram 通知。
- **错误处理原则**：
  - 网络错误（Binance/Telegram/OpenRouter）：捕获异常，记录 `logging.warning` 或 `logging.error`，尽量让下一轮迭代自动重试，而不是退出进程。
  - 致命配置错误（缺少 API Key 或 Hyperliquid 私钥）：在启动阶段直接 `logging.critical` 并终止，避免以未知状态运行。
  - 对 LLM 决策解析失败：记录具体错误原因与原始返回，拒绝下单，并保持组合状态一致。
  - 对每条严重错误，可使用 `notify_error` 将摘要转发到 Telegram，便于人工介入。

---

### 7.6 位置模式（Location Patterns）

- **配置与密钥**：
  - 所有敏感信息（API Key、私钥等）必须通过 `.env` 或运行环境注入，禁止写入代码或 git 版本库。
  - 新增配置项时，应在 `.env.example` 与文档中列出，并在代码中提供合理默认值或显式错误提示。
- **运行期数据**：
  - 统一使用 `TRADEBOT_DATA_DIR` 指定的根目录（默认 `./data`），回测则使用 `data-backtest/` 及其 `run-*` 子目录。
  - 不在代码仓库中创建额外的「临时」数据根目录，避免 agent 分叉出多套路径。
- **文档位置**：
  - 产品视角：`docs/prd.md`。
  - 架构视角：`docs/architecture/` 下分片文档。
  - 其它文档（如 project-overview / source-tree）应从架构文档或 index 链出，避免孤立文件。

---

### 7.7 一致性模式（Consistency Patterns）

- **时间与货币展示**：
  - 数值统一使用小数格式，余额/PNL 以 USD 计价，保留 2 位小数（如 `$1234.56`）。
- **日志格式**：
  - Python 日志使用统一格式：`%(asctime)s | %(levelname)s | %(message)s`，便于日志聚合与筛选。
  - 对同一类事件（例如 LLM 调用失败）使用一致的日志前缀，便于 grep/监控。
- **用户可见文本**：
  - CSV/JSON 字段与 UI 文本均使用英文，架构/PRD 文档使用中文描述为主。
  - 避免在代码与文档中混用多种语言描述同一概念，以减少歧义。

---

### 7.8 测试与校验模式（Testing Patterns）

> 当前仓库尚未包含正式的自动化测试，本节为推荐实践，供未来扩展时遵循。

- 优先为以下逻辑添加单元测试：
  - 指标计算函数（如 RSI/EMA/MACD/ATR）。
  - 风险与仓位计算逻辑（单笔风险上限、保证金计算等）。
  - CSV/JSON 读写与迁移逻辑（确保列结构变更不会破坏旧数据）。
- 测试入口：
  - 使用 pytest，在项目根目录运行 `pytest` 时默认加载 `tests/` 下的测试。
- Smoke / 集成测试：
  - Hyperliquid 集成可通过 `scripts/manual_hyperliquid_smoke.py` 手动验证；禁止将其纳入自动化 CI。

---

### 7.9 技术栈与版本策略（Technology Stack & Versions）

- **运行时与依赖（截至 2025-11-26，本仓库中实际使用的版本）**：
  - 运行时：Python `3.13.3`（Docker 基础镜像：`python:3.13.3-slim`）。
  - 关键依赖（摘自 `requirements.txt`）：
    - `python-binance==1.0.19`
    - `pandas==2.2.3`
    - `numpy==2.1.3`
    - `requests==2.31.0`
    - `python-dotenv==1.0.0`
    - `colorama==0.4.6`
    - `streamlit==1.38.0`
    - `hyperliquid-python-sdk>=0.9.0`
    - `eth-account>=0.10.0`
- **外部服务与协议**：
  - 行情：Binance REST API（现货/合约 K 线）。
  - LLM：OpenRouter → DeepSeek Chat V3.1（默认模型：`deepseek/deepseek-chat-v3.1`）。
  - 实盘执行：Hyperliquid Perpetuals。
  - 通知：Telegram Bot API。
- **版本管理原则**：
  - 新增技术决策时，必须在架构决策表中记录：技术名称、选定版本范围（或最小版本）、简要理由。
  - 更新依赖版本时，应：
    1. 修改 `requirements.txt`；
    2. 在架构决策表中更新对应行的版本号与「最近验证日期」。
  - 若未来引入数据库或 Web 框架，应在本节补充其版本与兼容性分析。

---

上述模式与规则不要求一次性重构现有代码，但所有新实现应尽量遵守；当旧代码与本约定不一致时，应优先通过重构逐步对齐，而不是在代码中创造第三套风格。
