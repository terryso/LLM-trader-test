# Story 9.3: 基于 `MARKET_DATA_BACKEND` 的 symbol 校验

Status: Ready for Review

## Story

As a developer integrating exchange/data backends,
I want symbol validation to respect the current `MARKET_DATA_BACKEND`,
So that a symbol is only added if it is supported by the active market data source.

作为负责集成交易所 / 市场数据 backend 的开发者，
我希望 symbol 校验逻辑能够严格遵循当前生效的 `MARKET_DATA_BACKEND`，
从而只有在**当前行情数据源实际支持**某个交易对时，才允许将其加入 Paper / Live 交易 Universe。

## Acceptance Criteria

1. **AC1：基于 `MARKET_DATA_BACKEND` 的统一校验入口（核心函数语义）**  
   - Given 已在 `config/universe.py` 中提供函数：`validate_symbol_for_universe(symbol: str) -> tuple[bool, str]`  
   - And `config.settings.get_effective_market_data_backend()` 已正确反映当前生效的 `MARKET_DATA_BACKEND`（支持 runtime overrides）  
   - When 在 Paper / Live 模式下调用 `validate_symbol_for_universe("BTCUSDT")`  
   - Then 该函数会：  
     - 先进行**本地静态校验**：若 symbol 不在 `SYMBOL_TO_COIN` 中，直接返回 `(False, <错误信息>)`；  
     - 再根据当前 `MARKET_DATA_BACKEND` 分支到相应 backend 的校验逻辑（Binance / Backpack）；  
     - 成功时返回 `(True, "")`；失败时返回 `(False, <包含 backend 与原因的错误信息>)`。  

2. **AC2：Binance backend 下的 symbol 校验行为（USDT 计价规范）**  
   - Given `MARKET_DATA_BACKEND=binance`（或 runtime override 生效为 `"binance"`）  
   - And `validate_symbol_for_universe` 使用 Binance 行情客户端或等价能力进行校验（例如基于 `BinanceMarketDataClient` / 交易所元数据）  
   - When 传入典型合法 symbol，如 `BTCUSDT`、`ETHUSDT`、`SOLUSDT`  
   - Then：  
     - 返回值 `(True, "")`；  
     - 内部实现不会因为网络抖动/临时 API 错误而抛出异常到调用方，而是记录日志并返回带原因的 `(False, error)` 或合理的重试/降级结果。  
   - And When 传入明显非法 symbol，如 `INVALIDUSDT`  
   - Then：  
     - 返回 `(False, error)`；  
     - `error` 文案中包含 `backend: binance` 或等价 backend 标识，以及「不被当前 backend 支持」之类的原因描述。  

3. **AC3：Backpack backend 下的 symbol 校验行为（USDC 合约规范 + 映射）**  
   - Given `MARKET_DATA_BACKEND=backpack`（或 runtime override 生效为 `"backpack"`）  
   - And Universe 与 Telegram `/symbols` 命令层仍使用 `BTCUSDT` 风格符号作为用户-facing 约定  
   - When 调用 `validate_symbol_for_universe("BTCUSDT")`  
   - Then 校验逻辑会：  
     - 使用与 `BackpackMarketDataClient._normalize_symbol` 一致的规则，将 `BTCUSDT` 映射到 Backpack 实际使用的 `BTC_USDC_PERP` 或等价符号；  
     - 基于 Backpack 行情/市场元数据接口（如 markPrices、klines、openInterest 等）验证该合约是否存在；  
     - 若存在，则返回 `(True, "")`；若不存在，则返回 `(False, error)`，其中 `error` 至少包含 `backend: backpack` 与失败原因。  
   - And When 传入对 Backpack 不合法的符号（如 `ABCXYZUSDT`），即便其在 `SYMBOL_TO_COIN` 中，也必须被拒绝：  
     - 返回 `(False, error)`，清晰说明「在 Backpack 对应 USDC 合约列表中未找到」。  

4. **AC4：与 `/symbols` 命令的集成与错误反馈（对接 Story 9.2）**  
   - Given Story 9.2 已实现 `/symbols add` 命令，并在内部调用 `validate_symbol_for_universe` 进行符号合法性校验  
   - When 管理员在 Telegram 中执行：`/symbols add BTCUSDT`  
   - Then：  
     - 若当前 backend 真正支持 `BTCUSDT`（Binance）或其 Backpack 等价合约，则校验通过并将 symbol 合并进 Universe；  
     - 若当前 backend 不支持，则 `/symbols add` 返回错误提示，包含：  
       - 当前 backend 类型（`binance` / `backpack`）；  
       - 后端返回或推断的失败原因（如 symbol 不存在、合约未上线等）；  
       - 保持现有测试中对「无效 symbol」文案的兼容（例如仍包含「无效」或「不在已知交易对列表中」等关键词），避免破坏用户预期。  

5. **AC5：最小测试覆盖（至少两种 backend）**  
   - Given 运行 `./scripts/run_tests.sh`  
   - When 为 Story 9.3 新增/扩展测试（推荐主要集中在 `tests/test_universe.py` 与 `tests/test_telegram_symbols_commands.py`）  
   - Then 至少覆盖：  
     - `MARKET_DATA_BACKEND=binance` 场景下：  
       - 典型已知 symbol 返回 `(True, "")`；  
       - 明显非法 symbol 返回 `(False, error)`，且 error 中包含 `backend: binance`。  
     - `MARKET_DATA_BACKEND=backpack` 场景下：  
       - 通过模拟或 mock Backpack 行情接口，验证 BTC/ETH 等 USDC 合约校验行为；  
       - 非法 symbol 返回 `(False, error)`，且 error 中包含 `backend: backpack`。  
     - `/symbols add` 在两种 backend 下的集成路径：校验成功/失败时的行为与文案。  
   - And 所有现有 Universe / Telegram 相关测试在不更新预期前提下不应被无意破坏；若需调整断言，应在测试中明确注释与本 Story 的关系。  

6. **AC6：安全与可观测性约束**  
   - Given `validate_symbol_for_universe` 可能在 Telegram 命令或其它热路径中被频繁调用  
   - When 实现 backend 级别的实际 API 校验逻辑  
   - Then：  
     - 不会在**正常错误场景**（symbol 不存在、HTTP 4xx/5xx、解析失败等）抛出未捕获异常；  
     - 会使用适当的日志级别记录失败原因（DEBUG/INFO 用于预期错误，WARNING 用于配置错误或 API 行为异常）；  
     - 对潜在的频繁调用场景提供至少最小程度的缓存或轻量化策略（例如重用已有 market data client、避免重复初始化重型对象），并在 Dev Notes 中给出建议。  

## Tasks / Subtasks

- [x] **Task 1：细化 `validate_symbol_for_universe` 的 backend 分支逻辑**  
  - [x] 在 `config/universe.py` 中扩展 `validate_symbol_for_universe`：  
    - [x] 先执行静态校验：若 symbol 不在 `SYMBOL_TO_COIN`，直接返回 `(False, error)`，保留当前行为；  
    - [x] 再调用 `get_effective_market_data_backend()` 获取当前 backend（binance/backpack），并基于其分支到具体实现；  
    - [x] 对未知 backend（未来扩展）给出清晰错误信息和 TODO 提示，而不是静默通过。  

- [x] **Task 2：Binance backend 校验实现**  
  - [x] 评估并选择基于 Binance 行情/元数据接口的校验策略，例如：  
    - 通过 `BinanceMarketDataClient` 的 `get_klines` 做最小行情探测（limit 非常小、interval 短）；或  
    - 通过底层 ccxt / Binance Futures 客户端查询合约元数据（若已有现成工厂或 helper）。  
  - [x] 在实现中注意：  
    - [x] 所有网络错误、解析错误都通过日志记录并返回 `(False, error)`，不抛出异常给 `/symbols` 调用方；  
    - [x] 将 backend 类型与具象错误原因（如「Binance 返回 code=...」）拼入 `error` 字符串。  

- [x] **Task 3：Backpack backend 校验实现**  
  - [x] 复用 `exchange.market_data.BackpackMarketDataClient` 的 symbol 规范与 HTTP 接口：  
    - [x] 遵循 `_normalize_symbol` 的符号转换规则，将 `BTCUSDT` 映射为 `BTC_USDC_PERP` 等 Backpack 风格 symbol；  
    - [x] 选择一个轻量级 endpoint（如 `markPrices` 或 `openInterest`）检测 symbol 是否存在；  
    - [x] 对不存在的 symbol 返回 `(False, error)`，error 中提及 `backend: backpack`。  
  - [x] 注意与 Story 9.1 的 Universe 设计约束对齐：Universe override 仍然只能是 `SYMBOL_TO_COIN` 的子集，但 Backpack 校验可以进一步过滤「当前 backend 不支持」的子集。  

- [x] **Task 4：与 `/symbols` 命令的集成与回归验证**  
  - [x] 检查 `notifications/telegram_commands.py` 中 `/symbols add` 的实现，确认：  
    - [x] 调用 `validate_symbol_for_universe` 的位置统一且易于 mock 测试；  
    - [x] 无需在 handler 内重复实现 backend-specific 逻辑，一切都下沉到 `config.universe`。  
  - [x] 确保在 symbol 校验失败时，`/symbols add` 的错误提示：  
    - [x] 不会泄露敏感配置或 API 密钥信息；  
    - [x] 仍然满足 Story 9.2 中关于文案的基本期望（提示「无效」/「不被支持」，并建议查看 `/symbols list`）。  

- [x] **Task 5：测试补充与稳定性验证**  
  - [x] 在 `tests/test_universe.py` 中新增针对 `validate_symbol_for_universe` 的 backend-aware 测试：  
    - [x] 使用 `config.runtime_overrides.set_runtime_override("MARKET_DATA_BACKEND", "binance")` / `"backpack"` 控制环境；  
    - [x] 使用 `unittest.mock` 或等价机制对真实 HTTP / Binance 客户端进行 mock，避免测试访问外部网络；  
    - [x] 覆盖合法/非法 symbol 以及错误路径下的错误信息格式。  
  - [x] 在 `tests/test_telegram_symbols_commands.py` 中补充/调整测试：  
    - [x] 验证 `/symbols add` 在不同 backend 下能正确透传 `validate_symbol_for_universe` 的错误文案要点（包含 backend 与原因）；  
    - [x] 保持对现有 AC（权限控制、审计日志等）的回归测试。  

- [x] **Task 6：文档与架构对齐**  
  - [x] 在需要时更新 `docs/epics.md` 或相关架构文档中对 Story 9.3 的实现小结，可选：  
    - [x] 补充一两句说明「symbol 校验严格尊重 `MARKET_DATA_BACKEND`，并通过行情/元数据接口做二次确认」；  
  - [x] 在本 Story 文件完成实现后，将 `Status` 更新为 `done`，并在 Dev Agent Record 的 Completion Notes 中补充实现摘要与测试结论。

## Dev Notes

- **现有相关能力与上下文**  
  - 配置层：  
    - `config/settings.py` 定义并解析 `MARKET_DATA_BACKEND`，当前支持值为 `"binance"` 与 `"backpack"`；  
    - `get_effective_market_data_backend()` 提供 runtime override 感知的 backend 读取入口。  
  - Universe 抽象（Story 9.1）：  
    - `config/universe.py` 提供：  
      - `set_symbol_universe` / `clear_symbol_universe_override` / `get_effective_symbol_universe` / `get_effective_coin_universe`；  
      - Universe override 只能选择 `SYMBOL_TO_COIN` 的子集，未知 symbol 会被忽略并记录 WARNING；  
      - **空 Universe 语义**：显式空列表代表「不再开新仓」，而非回退到默认 Universe。  
  - `/symbols` 命令（Story 9.2）：  
    - `notifications/telegram_commands.py` 中已实现：  
      - `handle_symbols_command`、`handle_symbols_list_command`、`handle_symbols_add_command`、`handle_symbols_remove_command` 等；  
      - 审计日志 `_log_symbols_audit` 以及管理员校验 `_check_symbols_admin_permission`；  
    - `tests/test_telegram_symbols_commands.py` 已对 `/symbols list/add/remove` 行为提供较完备测试。  
  - 当前 `validate_symbol_for_universe` 行为（Story 9.2 占位实现）：  
    - 使用 `SYMBOL_TO_COIN` 作为「已知 symbol」的静态白名单；  
    - 对不在 `SYMBOL_TO_COIN` 中的 symbol 返回 `(False, error)`，并在 error 中包含 backend 信息；  
    - 尚未真正对接 Binance / Backpack 的行情或合约元数据校验，是 Story 9.3 的主要工作内容。  

- **Backend 具体实现线索**  
  - Binance：  
    - `exchange/market_data.py` 中的 `BinanceMarketDataClient` 已封装部分行情接口：  
      - `get_klines(symbol, interval, limit)`；  
      - `get_funding_rate_history` / `get_open_interest_history`（均为防御性实现，遇到异常返回空列表并记录日志）。  
    - 建议沿用类似的防御性模式：  
      - 调用方不依赖具体异常类型，而依赖返回值与日志；  
      - 在 symbol 校验场景中将「无法确认」视为失败（返回 False + error），而不是乐观通过。  
  - Backpack：  
    - `exchange/market_data.py` 中的 `BackpackMarketDataClient` 已实现：  
      - `_normalize_symbol`：将 `BTCUSDT` 规范化为 Backpack 风格的 `BTC_USDC_PERP`；  
      - `get_klines` / `get_funding_rate_history` / `get_open_interest_history`，均对网络错误做了防御性处理。  
    - Story 9.3 的实现可复用 `_normalize_symbol` 和一个轻量的 endpoint（如 `markPrices` 或 `openInterest`）来判断 symbol 是否存在。  

- **架构边界与设计建议**  
  - symbol 校验应被视为「配置与 Universe 层」的责任，而非 Telegram handler 自己的逻辑：  
    - `/symbols` 命令只负责参数解析、权限控制与用户消息构建；  
    - 实际「某 symbol 是否被当前 backend 支持」应完全由 `config.universe.validate_symbol_for_universe` 决定。  
  - 建议通过依赖注入或工厂函数获取 market data client，而不是在 `config.universe` 中直接创建底层 HTTP 客户端：  
    - 例如在调用层（如 Telegram handler 或更高一层的 service）中注入一个「symbol 校验 service」，由该 service 内部组合 `validate_symbol_for_universe` 与具体的 `BinanceMarketDataClient` / `BackpackMarketDataClient`；  
    - 若暂不引入完整 service，可在 `config.universe` 中保持实现尽可能轻量，并为未来重构预留扩展点。  

- **测试与可观测性注意事项**  
  - 所有对外依赖（Binance 客户端、Backpack HTTP 请求）都应在单元测试中通过 mock 隔离：  
    - 避免测试访问真实外部 API；  
    - 使用固定的 mock 响应模拟「symbol 存在 / 不存在 / API 出错」三种典型场景。  
  - 对 symbol 无效或 backend 不支持的情况，应使用 WARNING 级别日志记录关键信息（symbol、backend、原因），以便事后审计 `/symbols add` 失败的原因。  
  - 对正常失败（如用户手误输错 symbol）可以使用 INFO 或 DEBUG 级别日志，避免日志噪音过大。  

### Project Structure Notes

- 本 Story 主要涉及以下模块：  
  - `config/universe.py`：symbol 校验逻辑与 Universe 抽象所在的配置层；  
  - `config/settings.py`：`MARKET_DATA_BACKEND` 与相关 getter；  
  - `exchange/market_data.py`：各 backend 的行情客户端与符号规范化逻辑；  
  - `notifications/telegram_commands.py`：`/symbols` 命令与审计日志；  
  - `tests/test_universe.py`、`tests/test_telegram_symbols_commands.py`：测试与契约校验。  
- 需要遵守 `docs/architecture/06-project-structure-and-mapping.md` 与 `07-implementation-patterns.md` 中的约定：  
  - 配置相关逻辑优先放在 `config/` 层；  
  - 交易所与行情客户端逻辑集中在 `exchange/` 层；  
  - 避免在 Telegram handler 中直接构造底层 HTTP 客户端。  

### References

- [Source: docs/epics.md#Story 9.3: 基于 `MARKET_DATA_BACKEND` 的 symbol 校验]
- [Source: docs/sprint-artifacts/9-1-可配置交易-universe-抽象-paper-live.md]
- [Source: docs/sprint-artifacts/9-2-telegram-symbols-命令接口-list-add-remove.md]
- [Source: config/universe.py]
- [Source: exchange/market_data.py]
- [Source: tests/test_universe.py]
- [Source: tests/test_telegram_symbols_commands.py]

## Dev Agent Record

### Context Reference

- 本 Story 文档由 `/create-story` 工作流基于 sprint-status 与 epics 自动生成。  
- 相关上下文文件：  
  - `docs/epics.md`（Epic 9 与 Story 9.3 源需求定义）；  
  - `docs/sprint-artifacts/sprint-status.yaml`（当前 sprint 状态跟踪）；  
  - `config/settings.py` / `config/universe.py` / `exchange/market_data.py`；  
  - `notifications/telegram_commands.py`；  
  - `tests/test_universe.py` / `tests/test_telegram_symbols_commands.py`。  

### Agent Model Used

Cascade

### Debug Log References

- 开发与调试建议：  
  - 在本地或测试环境中，将日志级别调整为 DEBUG 或 INFO，运行短时间 Paper 模式主循环；  
  - 通过 Telegram 手动测试 `/symbols add` 在不同 `MARKET_DATA_BACKEND` 下的行为（使用 mock 或测试环境 API Key）；  
  - 结合运行 `./scripts/run_tests.sh`，确保新增测试覆盖所有关键路径。  

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created for Story 9.3 symbol validation based on MARKET_DATA_BACKEND.
- **Story 9.3 Implementation Complete (2025-12-02)**:
  - 实现了 `validate_symbol_for_universe` 的 backend 分支逻辑，支持 binance 和 backpack 两种 backend
  - Binance 校验：使用 `BinanceMarketDataClient.get_klines` 进行轻量级 symbol 存在性检测
  - Backpack 校验：使用 `BackpackMarketDataClient._get_mark_price_entry` 和 `_normalize_symbol` 进行 USDC 合约校验
  - 所有网络错误、解析错误都通过日志记录并返回 `(False, error)`，不抛出异常
  - 错误信息包含 backend 类型和具体原因，便于用户排查
  - 对未知 backend 给出清晰的 TODO 提示
  - 新增 4 个测试类共 20+ 个测试用例，覆盖 AC1-AC6 所有验收标准
  - 所有 862 个测试通过，无回归
- **Code Review 重构 (2025-12-02)**:
  - **架构分层优化**: 将 backend 校验逻辑从 `config` 层移至 `exchange` 层，新建 `exchange/symbol_validation.py` 模块
  - **客户端单例复用**: `SymbolValidationService` 维护 per-backend 单例客户端，避免重复初始化
  - **Symbol 级别 TTL 缓存**: 默认 5 分钟缓存，减少重复 API 调用；网络错误不缓存
  - **公开 API 替代私有方法**: `BackpackMarketDataClient` 新增 `symbol_exists()` 公开方法
  - **错误语义区分**: `ValidationErrorType` 枚举区分 `SYMBOL_NOT_FOUND`、`NETWORK_ERROR`、`API_ERROR`、`UNKNOWN_BACKEND`
  - **契约性测试**: 新增 `TestSymbolValidationContractNeverRaises` 确保不抛异常
  - 所有 880 个测试通过，无回归

### Change Log

- 2025-12-02: Story 9.3 实现完成 - 基于 MARKET_DATA_BACKEND 的 symbol 校验
- 2025-12-02: Code Review 重构 - 架构分层优化、客户端复用、缓存、错误语义区分

## Tech Debt / Future Work

- **Backpack base URL 运行时切换**  
  - 当前 `BackpackMarketDataClient` 由 `SymbolValidationService` 以单例方式创建，`BACKPACK_API_BASE_URL` 只在首次创建客户端时读取一次；  
  - 若未来需要通过 runtime overrides 或配置热更新来切换 Backpack API base URL（测试 / 生产 / 代理等环境），建议单独拆分 Story：
    - 提供显式的 `reset_backpack_client()` / 重新注入入口，用于在切换环境时刷新单例；  
    - 或通过工厂 / 依赖注入方式提供 `BackpackMarketDataClient`，避免在 service 内部直接依赖全局常量。  

- **Backpack markPrices 请求逻辑复用**  
  - 目前 `BackpackMarketDataClient._get_mark_price_entry` 与 `symbol_exists()` 都在调用 `/api/v1/markPrices` 并实现各自的请求与 JSON 解析逻辑；  
  - 为降低维护成本、避免 API 行为变更时出现微妙不一致，后续可以考虑：
    - 抽取一个私有 helper（如 `_fetch_mark_prices(symbol)`），统一处理 HTTP 请求与 JSON 解析；  
    - `_get_mark_price_entry` 与 `symbol_exists()` 复用该 helper，只在各自层面做不同封装与错误语义映射。  

### File List

**新增的文件：**
- `exchange/symbol_validation.py` - Symbol 校验服务模块，包含 `SymbolValidationService`、`ValidationResult`、`ValidationErrorType` 等
- `tests/test_symbol_validation.py` - Symbol 校验服务测试，包含缓存、客户端复用、契约性测试等

**修改的文件：**
- `config/universe.py` - 重构 `validate_symbol_for_universe` 委托给 `exchange.symbol_validation` 模块
- `exchange/market_data.py` - `BackpackMarketDataClient` 新增 `symbol_exists()` 公开方法
- `tests/test_universe.py` - 更新测试适配新架构
- `tests/test_telegram_symbols_commands.py` - 更新 mock 路径适配新架构
- `docs/sprint-artifacts/sprint-status.yaml` - 更新 9-3 状态为 review
- `docs/sprint-artifacts/9-3-基于-market-data-backend-的-symbol-校验.md` - 本 Story 文件

**引用的现有文件（未修改）：**
- `config/settings.py` - MARKET_DATA_BACKEND 配置与 getter
- `notifications/telegram_commands.py` - `/symbols` 命令及对 `validate_symbol_for_universe` 的调用  
