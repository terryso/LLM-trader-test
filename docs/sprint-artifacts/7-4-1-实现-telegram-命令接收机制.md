# Story 7.4.1: 实现 Telegram 命令接收机制

Status: done

## Story

As a system,
I want to receive and parse Telegram commands,
so that users can remotely control the bot and its risk-control features.

## Acceptance Criteria

1. **AC1 – 基础命令轮询与解析（对齐 Epic 7.4 / Story 7.4.1 / PRD FR22）**  
   - 在正确配置 `TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID` 时：  
     - 新增模块 `notifications/telegram_commands.py`，提供 `TelegramCommandHandler` 类或等价抽象，用于从 Telegram Bot API 拉取和解析命令；  
     - 通过 Telegram Bot API 的 `getUpdates` 接口进行轮询，使用 `offset` / `last_update_id` 机制确保每条更新只处理一次；  
     - 仅处理 `message` 类型更新（文本消息），忽略其他类型（如回调查询），不会抛出异常；  
     - 对以 `/` 开头的文本消息进行解析，至少拆解出：  
       - `command`（去掉前导 `/` 的命令名，例如 `kill`、`resume`、`status` 等）；  
       - `args`（按空格拆分的参数列表，例如 `["confirm"]`）；  
       - `chat_id`、`message_id`、原始文本与原始 payload；  
     - 返回的结果使用简单且可测试的数据结构（例如 `TelegramCommand` dataclass 或带固定字段的字典）。

2. **AC2 – 与主循环集成（对齐 Epic 7.1 / 7.4 与 PRD「集成点 4. Telegram 集成」）**  
   - 在 `bot.py` 的主循环 `_run_iteration()` 中，在获取行情 / 风控检查等核心逻辑之前增加命令轮询步骤：  
     - 当且仅当存在有效的 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 配置时，构造一个 `TelegramCommandHandler` 实例；  
     - 在每次迭代开始时调用 `poll_commands()` 或等价方法，获取自上次迭代以来的新命令列表；  
     - 对于当前 Story，仅要求将解析后的命令安全地传递给后续处理入口（例如 `process_telegram_commands(commands)` 或回调），而**不在本 Story 中实现 /kill、/resume、/status 等具体业务逻辑**（这些属于 Stories 7.4.2–7.4.5 的范围）；  
     - 确保在纸上交易 / 回测 / 实盘三种模式下，命令轮询不会显著拖慢每轮迭代（例如合理设置超时、限制单次拉取的更新数量）。

3. **AC3 – 安全与健壮性（为 Story 7.4.5 打基础，对齐 PRD FR23–FR24 的技术约束）**  
   - `TelegramCommandHandler` 从配置中接收允许的 `allowed_chat_id`（对应 `TELEGRAM_CHAT_ID`），并在命令层面做**最小可用的预过滤**：  
     - 仅将来自 `allowed_chat_id` 的命令返回给调用方；  
     - 对于来自其他 Chat 的命令，记录 `WARNING` 级别日志并静默丢弃，不抛出异常；  
   - 在命令轮询与解析过程中发生的所有网络或解析错误（如请求超时、4xx/5xx 响应、非预期 payload 结构）：  
     - 使用 `WARNING` 或 `ERROR` 日志记录 HTTP 状态码、错误信息与简要上下文（例如 `update_id` / `chat_id`）；  
     - 错误不会导致 `_run_iteration()` 失败或提前退出，本轮命令处理视为失败但主循环继续。  
   - 单元测试至少覆盖：  
     - 典型命令文本 `/kill`、`/resume confirm`、`/status`、`/reset_daily`、`/help` 的解析结果（`command` 与 `args`）；  
     - 不同 `chat_id` 下，只有与配置的 `allowed_chat_id` 匹配的命令会被返回；  
     - `last_update_id` / `offset` 机制确保重复调用 `poll_commands()` 时不会多次返回同一条命令。

4. **AC4 – 测试与文档挂钩**  
   - 新增测试文件 `tests/test_notifications_telegram_commands.py` 或等价位置，覆盖 AC1–AC3 中提到的正常路径与关键异常路径；  
   - 运行 `./scripts/run_tests.sh` 时，所有既有测试与本 Story 新增测试均通过；  
   - Dev Notes 中明确引用并链接到以下文档章节：  
     - `docs/epic-risk-control-enhancement.md#Story-7.4.1-实现-Telegram-命令接收机制`；  
     - `docs/prd-risk-control-enhancement.md#Telegram-命令集成`（或相邻描述命令接入的章节）；  
     - `docs/epics.md#Epic-7.4-Telegram-命令集成-Post-MVP`。

## Tasks / Subtasks

- [x] **Task 1 – 设计并实现 Telegram 命令处理器（AC1, AC3）**  
  - [x] 1.1 在 `notifications/telegram_commands.py` 中定义 `TelegramCommand` 数据结构（或等价字典约定），包含 `command`、`args`、`chat_id`、`message_id`、`raw_text`、`raw_update` 等字段；  
  - [x] 1.2 实现 `TelegramCommandHandler`：  
        - 管理 `bot_token`、`allowed_chat_id` 与 `last_update_id`；  
        - 封装调用 Telegram Bot API `getUpdates` 的 HTTP 请求逻辑；  
        - 从返回的 `result` 数组中过滤并解析命令。  
  - [x] 1.3 为异常与错误场景设计统一的日志格式（等级、字段），与现有 `notifications/telegram.py` 中的日志风格保持一致。

- [x] **Task 2 – 将命令轮询集成到主循环（AC2）**  
  - [x] 2.1 在 `config/settings.py` 或等价配置模块中复用 / 补充 Telegram 相关环境变量读取逻辑，确保命令接收与现有通知共享同一 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 语义；  
  - [x] 2.2 在 `bot.py` 的 `_run_iteration()` 中，根据配置构造 `TelegramCommandHandler` 并调用其 `poll_commands()`（或通过更高层封装、辅助函数完成）；  
  - [x] 2.3 设计一个中立的命令分发入口（例如 `process_telegram_commands(commands)` 或回调参数），本 Story 仅负责**触发与传递**，不直接操作 `RiskControlState` 或执行 /kill 等业务动作；  
  - [x] 2.4 在 Dev Notes 中记录命令轮询在主循环中的调用顺序与错误处理策略，方便后续 Stories 7.4.2–7.4.5 复用。

- [x] **Task 3 – 单元测试与运行验证（AC3, AC4）**  
  - [x] 3.1 在 `tests/test_notifications_telegram_commands.py` 中新增针对命令解析与 chat 过滤的测试；  
  - [x] 3.2 使用模拟 HTTP 客户端 / monkeypatch 方式，为 `getUpdates` 调用构造成功 / 失败 / 非法 payload 场景，并验证错误处理与日志行为；  
  - [x] 3.3 运行 `./scripts/run_tests.sh`，确保全部测试通过，并在 Dev Notes 的 Change Log 中记录一次成功运行。

## Dev Notes

### Requirements & Context Summary

- 本 Story 属于 **Epic 7.4: Telegram 命令集成** 的首个实现 Story，对应 `sprint-status.yaml` 中的 key：`7-4-1-实现-telegram-命令接收机制`。  
- 需求主要来源：  
  - PRD 《风控系统增强 - 产品需求文档》（`docs/prd-risk-control-enhancement.md`）中的 **「Telegram 命令集成」** 与相关 FR：  
    - **FR22**：系统支持通过 Telegram Webhook 或轮询方式接收用户命令，本 Story 选择使用 Telegram 官方 `getUpdates` 轮询模式实现最小可用路径；  
    - **FR23**：系统仅响应来自配置 `TELEGRAM_CHAT_ID` 的命令，本 Story 在命令接收层提供基础过滤，后续 Story 7.4.5 会在命令处理层补充更严格的安全校验；  
    - **FR24**：未知命令返回帮助信息，本 Story 只负责「正确解析并转交命令」，具体帮助文案与行为由 Story 7.4.5 完成。  
  - Epic 文档 `docs/epic-risk-control-enhancement.md` 中 **Story 7.4.1: 实现 Telegram 命令接收机制** 的拆解：  
    - 建议新增 `TelegramCommandHandler` 类，使用 `getUpdates` 轮询并在每轮主循环开始时检查新命令；  
    - 要求将命令解析为结构化对象，供后续 /kill、/resume、/status、/reset_daily、/help 等命令处理 Story 复用。  
  - `docs/epics.md` 中 **Epic 7.4: Telegram 命令集成** 的范围说明：  
    - 本 Epic 负责为已有的 Kill-Switch / 每日亏损限制能力提供远程控制入口；  
    - 7.4.1 专注于「命令接收基础设施」，7.4.2–7.4.5 则实现具体命令处理逻辑与安全策略。  
- 与前序 Stories 的关系：  
  - Epic 7.1 / 7.2 / 7.3 已实现风控状态模型、Kill-Switch、每日亏损限制与相关通知机制（详见 `docs/sprint-artifacts/7-3-4-实现每日亏损限制通知.md` 等 Story 文档）；  
  - 这些能力已通过 Telegram 单向通知暴露给用户，本 Story 是从「通知」走向「命令控制」的第一步，重点是**可靠地把 Telegram 命令输入到系统内部**，而非改变任何现有风控语义。

### Architecture & Implementation Constraints

- **模块边界与职责分配：**  
  - `notifications/telegram.py`：继续专注于「发送通知」与复用型发送 helper（包括 Markdown 降级重试等），本 Story 不在该模块中实现命令解析逻辑；  
  - `notifications/telegram_commands.py`：集中负责「命令接收与解析」逻辑，包括调用 Telegram Bot API、维护 `last_update_id`、解析文本命令等；  
  - `bot.py`：负责在 `_run_iteration()` 中装配命令处理器，并将解析出的命令传递给后续处理层，不直接关心 Telegram 细节；  
  - 后续 Stories（7.4.2–7.4.5）可以在单独模块中实现具体命令的业务语义（操作 `RiskControlState`、更新状态、回复消息等）。  
- **一致性要求：**  
  - 网络调用与错误处理方式应与 `notifications/telegram.py` 中现有的 Telegram 发送逻辑保持一致：使用统一的日志前缀、等级与字段，避免「静默失败」；  
  - 命令解析采用尽量简单的语法（以空格分隔参数），在后续 Story 中扩展时不破坏向后兼容；  
  - 不在命令接收层做复杂业务判断或状态修改，只做**输入规范化**与**安全过滤**。  
- **禁止事项：**  
  - 禁止在本 Story 中直接修改 `RiskControlState` 或调用 `activate_kill_switch` / `deactivate_kill_switch` 等风控 API；  
  - 禁止在命令处理线程/协程中执行长耗时操作（如回测、复杂计算），所有长任务应通过后续 Stories 定义的机制处理；  
  - 禁止在遇到单条更新解析失败时中断整个 `getUpdates` 结果的处理，应跳过该条并记录日志。

### Project Structure Notes

- 预计主要涉及文件（最终以实际实现为准）：  
  - `notifications/telegram_commands.py` —— 新增命令接收与解析模块；  
  - `notifications/telegram.py` —— 仅在需要共享配置 / HTTP 客户端时适度复用，不在本 Story 中大改结构；  
  - `bot.py` —— 在 `_run_iteration()` 开始阶段集成命令轮询入口；  
  - `config/settings.py` —— 确保 Telegram 相关环境变量与命令接收使用相同来源与默认值；  
  - `tests/test_notifications_telegram_commands.py` —— 新增命令解析与错误处理的单元测试。  
- 整体结构应继续遵守 `docs/architecture/06-project-structure-and-mapping.md` 与 `docs/architecture/07-implementation-patterns.md` 中的约定，尤其是：  
  - 对外部服务（Telegram API）使用清晰的适配层；  
  - 保持主循环简洁，将细节封装在独立模块中；  
  - 使用 UTC 时间与结构化日志文本。

### Learnings from Previous Story

- **前一 Story:** 根据 `sprint-status.yaml` 的顺序，上一条已完成的 Story 是 `7-3-4-实现每日亏损限制通知`（状态为 `done`，详见 `docs/sprint-artifacts/7-3-4-实现每日亏损限制通知.md`）。  
- **可复用能力与约束：**  
  - Telegram 通知路径已经在 `notifications/telegram.py` 中建立，包括：消息格式、MarkdownV2 兼容性处理、失败时的降级重试与日志模式；本 Story 在实现命令接收时，应沿用相同的 HTTP 客户端与日志约定，避免另起一套调用栈。  
  - 每日亏损限制通知的文案中已经向用户暴露了 `/resume confirm`、`/status`、`/reset_daily` 等命令名称，本 Story 在解析命令时需确保对这些命令名与参数形式提供稳定支持，为后续实现具体语义留好接口。  
  - 风控相关逻辑（Kill-Switch、每日亏损限制）已通过严格的单元与集成测试验证，本 Story 不应在命令接收层绕过这些入口或引入平行状态，应始终通过既有 `RiskControlState` 与 helper 接口触发行为（由后续 Stories 定义）。  
- **对本 Story 的启示：**  
  - 继续贯彻「通知失败不影响风控逻辑」的设计理念到命令接收侧：命令拉取或解析失败不应破坏主循环与本地风控状态；  
  - 在 Dev Notes 中保持对 PRD FR18–FR21 与既有实现的引用，便于后续 Stories 统一审查整个「通知 + 命令」闭环的风险与可观测性。

### References

- [Source: docs/epic-risk-control-enhancement.md#Story-7.4.1-实现-Telegram-命令接收机制]  
- [Source: docs/prd-risk-control-enhancement.md#Telegram-命令集成]  
- [Source: docs/epics.md#Epic-7.4-Telegram-命令集成-Post-MVP]  
- [Source: docs/sprint-artifacts/7-3-4-实现每日亏损限制通知.md]  
- [Source: docs/architecture/07-implementation-patterns.md]

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/7-4-1-实现-telegram-命令接收机制.context.xml`（由后续 `story-context` 工作流生成后填充）  
- (相关) `docs/epic-risk-control-enhancement.md#Story-7.4.1-实现-Telegram-命令接收机制`  
- (相关) `docs/prd-risk-control-enhancement.md#Telegram-命令集成`

### Agent Model Used

- Cascade（本 Story 草稿由 SM/AI 协同创建，用于指导后续 Dev Story 实施与代码评审）

### Debug Log References

- 命令接收路径中的日志行为建议：  
  - 当 Telegram 未配置或配置不完整时，输出 INFO 日志：`Telegram command polling skipped: Telegram not configured`；  
  - 当 `getUpdates` 调用失败或返回异常状态码时，输出 WARNING/ERROR 日志：`Failed to poll Telegram updates: <status>/<error>`；  
  - 当收到来自未授权 Chat ID 的命令时，输出 WARNING 日志：`Ignoring Telegram command from unauthorized chat: <chat_id>`；  
  - 当成功解析至少一条命令时，可在 DEBUG/INFO 级别记录摘要：`Telegram commands polled: N (last_update_id=...)`。

### Completion Notes List

- [x] **`TelegramCommandHandler` 最终 API 形态：**
  - `TelegramCommandHandler(bot_token, allowed_chat_id, last_update_id=0, timeout=5, limit=10)` - 构造函数
  - `poll_commands() -> List[TelegramCommand]` - 主轮询方法
  - `last_update_id` 属性 - 用于跟踪已处理的更新
  - `TelegramCommand` dataclass 包含: `command`, `args`, `chat_id`, `message_id`, `raw_text`, `raw_update`

- [x] **与 `notifications/telegram.py` 的关系：**
  - 独立模块，不共享 HTTP 会话（命令接收使用 GET，通知发送使用 POST）
  - 遵循相同的日志格式和错误处理模式（WARNING/ERROR 级别，不中断主循环）
  - 共享相同的配置来源（`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`）

- [x] **命令轮询在主循环中的调用顺序：**
  1. 迭代开始，打印 Header
  2. **`poll_telegram_commands()`** ← 在风控检查之前调用
  3. 风控检查 (`check_risk_limits`)
  4. SL/TP 检查
  5. LLM 调用和决策处理
  6. 状态保存

- [x] **错误处理策略：**
  - 网络错误、超时、4xx/5xx 响应：记录 WARNING 日志，返回空列表，主循环继续
  - 未授权 chat_id：记录 WARNING 日志，静默丢弃该命令
  - JSON 解析错误：记录 WARNING 日志，返回空列表
  - 命令处理器异常：记录 ERROR 日志，继续处理下一条命令

### File List

- **新增文件:**
  - `notifications/telegram_commands.py` — 命令接收与解析模块（~300 行）
  - `tests/test_notifications_telegram_commands.py` — 命令接收相关单元测试（~550 行，36 个测试用例）

- **修改文件:**
  - `notifications/__init__.py` — 添加 telegram_commands 模块导出
  - `bot.py` — 集成命令轮询入口（添加 `get_telegram_command_handler()`, `poll_telegram_commands()`, 在 `_run_iteration()` 中调用）

## Change Log

- 2025-11-30: 初始 Story 草稿由 `/create-story` 工作流基于 PRD / Epic / 架构文档生成，状态设为 `drafted`，等待后续 `story-context` 与 Dev Story 实施。
- 2025-12-01: Story 实现完成，所有 AC 验证通过：
  - AC1: 实现 `TelegramCommandHandler` 和 `TelegramCommand` dataclass，支持 `/kill`, `/resume confirm`, `/status`, `/reset_daily`, `/help` 等命令解析
  - AC2: 在 `bot.py` 的 `_run_iteration()` 中集成命令轮询，通过 `poll_telegram_commands()` 调用
  - AC3: 实现 chat_id 过滤、last_update_id 机制、完整的错误处理（网络错误、超时、4xx/5xx、JSON 解析错误）
  - AC4: 新增 36 个测试用例，全部 609 个测试通过（`./scripts/run_tests.sh`）
  - 状态更新: in-progress → review
- 2025-12-01: Senior Developer Review (AI) 完成，Outcome=Approve，状态更新: review → done。

## Senior Developer Review (AI)

### Reviewer & Outcome

- Reviewer: Nick（via Cascade AI）
- Date: 2025-12-01
- Outcome: Approve
- Summary:
  - 已实现独立的 `notifications/telegram_commands.py` 模块，对 Telegram `getUpdates` 进行短轮询，解析 `/kill`、`/resume confirm`、`/status`、`/reset_daily`、`/help` 等命令。
  - 在 `bot.py` 的 `_run_iteration()` 开始阶段集成命令轮询，并通过中立入口 `process_telegram_commands` 将命令传递给后续 Story 使用。
  - 覆盖 AC1–AC3 的正常路径与错误路径测试，所有现有测试（共 609 个）全部通过。

### Key Findings

#### High Severity

- 无高严重级别问题。

#### Medium Severity

- 无中严重级别问题。

#### Low Severity / Advisory

- 当前 Story 仅实现命令接收基础设施，不包含具体业务处理逻辑（/kill、/resume 等），与 Story 范围完全一致；后续 7.4.2–7.4.5 需要在此基础上补充业务处理与安全校验。
- 可在后续 Story 中考虑增加一个围绕 `_run_iteration()` 的集成测试，用 fake `TelegramCommandHandler` 验证在 Telegram 已配置与未配置两种情况下的调用行为（建议，非阻塞）。

### Acceptance Criteria Coverage

| AC # | 描述（简要） | 状态 | 证据 |
| ---- | ------------ | ---- | ---- |
| AC1 | `getUpdates` 轮询、仅处理 message+`/` 命令、解析为 `TelegramCommand` | IMPLEMENTED | `notifications/telegram_commands.py`:21-38,65-88,94-143,145-199,201-286；`tests/test_notifications_telegram_commands.py`:81-170,176-230 |
| AC2 | 在 `_run_iteration()` 早期集成命令轮询，并通过中立入口传递命令 | IMPLEMENTED | `notifications/telegram_commands.py`:289-311,314-351；`bot.py`:98-101,222-237,240-273,684-705 |
| AC3 | 仅返回允许 `chat_id` 的命令，其他 chat 记录 WARNING 并丢弃；网络/解析错误记录日志但不影响主循环 | IMPLEMENTED | `notifications/telegram_commands.py`:83-88,94-143,145-199,201-255；`tests/test_notifications_telegram_commands.py`:176-230,236-311,317-399,406-471 |
| AC4 | 新增测试文件覆盖 AC1–AC3 的正常与关键异常路径，完整测试集通过 | IMPLEMENTED | `tests/test_notifications_telegram_commands.py` 全文件；执行 `./scripts/run_tests.sh` 报告 609 tests passed |

**Acceptance Criteria Summary:** 4 / 4 个 AC 全部实现且有对应代码与测试证据。

### Task Completion Validation

| Task | 标记状态 | 验证状态 | 证据 |
| ---- | -------- | -------- | ---- |
| Task 1 – 设计并实现 Telegram 命令处理器 | [x] | VERIFIED COMPLETE | `notifications/telegram_commands.py`:21-38,65-88,94-143,145-199,201-286；日志与错误处理与 `notifications/telegram.py` 风格一致（WARNING/ERROR，不中断主循环） |
| Task 2 – 将命令轮询集成到主循环 | [x] | VERIFIED COMPLETE | `config/settings.py`:370-375（Telegram 配置）；`bot.py`:98-101,222-237,240-273,684-705；`notifications/telegram_commands.py`:289-311,314-351 |
| Task 3 – 单元测试与运行验证 | [x] | VERIFIED COMPLETE | `tests/test_notifications_telegram_commands.py`：命令解析、chat 过滤、last_update_id/offset、错误场景、消息过滤、工厂函数、分发与集成流测试；`./scripts/run_tests.sh` 全部通过 |

**Task Summary:** 3 / 3 个已勾选任务全部验证完成，未发现“打钩但未实现”的情况。

### Test Coverage and Gaps

- 覆盖点：
  - AC1：`TestCommandParsing` + `TestTelegramCommandDataclass` 覆盖典型命令（`/kill`、`/resume confirm`、`/status`、`/reset_daily`、`/help`）的解析与数据结构。
  - AC3：`TestChatIdFiltering`、`TestOffsetMechanism`、`TestErrorHandling` 覆盖允许/不允许 chat、offset/last_update_id 机制、HTTP 错误、超时、网络异常、JSON 解析错误与 `ok=false` 情况。
  - 消息过滤：`TestMessageTypeFiltering` 确保非 message 更新、非命令文本与空文本被忽略。
  - 分发逻辑：`TestProcessTelegramCommands` 验证无 handler 时的日志行为、命中 handler 的调用以及 handler 抛错时不会中断后续命令。
- 潜在补充点（建议，非必需）：
  - 增加一个围绕 `bot._run_iteration()` 的集成测试，使用 monkeypatch 注入假 `TelegramCommandHandler`，验证在 Telegram 配置开启/关闭两种场景下 `poll_telegram_commands()` 的调用行为。

### Architectural Alignment

- 外部服务边界：
  - 所有 Telegram `getUpdates` 调用集中在 `notifications/telegram_commands.py`，发送通知仍然在 `notifications/telegram.py`，符合 docs/architecture 中对 notifications 层的职责划分。
- 配置复用：
  - 命令接收与通知路径共同使用 `config/settings.py` 中的 `TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID`，保证语义一致。
- 主循环集成：
  - `_run_iteration()` 中在风控检查与 LLM 调用之前执行 `poll_telegram_commands()`，保持命令接收对核心交易逻辑的解耦，仅通过中立入口向后续 Story 暴露命令列表。

### Security Notes

- 访问控制：
  - `TelegramCommandHandler` 仅返回 `allowed_chat_id`（配置自 `TELEGRAM_CHAT_ID`）来源的命令，对其他 Chat 记录 WARNING 并丢弃，满足“仅响应配置 Chat ID” 的安全约束。
- 故障与日志：
  - 网络错误、超时、4xx/5xx、JSON 解析异常均被捕获并记录 WARNING，未在日志中泄露 bot token，仅输出状态码与错误文本/异常信息。
- 命令处理：
  - 本 Story 不对接任何风控状态或执行操作，后续命令逻辑由 7.4.2–7.4.5 实现，可在其上进一步补充权限与审计能力。

### Best-Practices and References

- 代码遵循 `docs/architecture/06-project-structure-and-mapping.md` 中对 Telegram 通知/集成的分层约定，将 HTTP 调用与命令解析集中在 notifications 层。
- 错误处理与日志风格与现有 `notifications/telegram.py` 对齐，避免“静默失败”，有利于在生产环境中排查网络或配置问题。
- 测试文件结构与现有 `tests/test_notifications_telegram.py` 一致，使用 pytest + mock requests 避免真实外部调用。

### Action Items

**Code Changes Required:**

- 无（本次评审未发现需要阻塞上线的代码修改项）。

**Advisory Notes:**

- Note: 建议在后续 Story 7.4.2–7.4.5 中补充一到两个围绕 `_run_iteration()` 的集成测试，用 fake `TelegramCommandHandler` 验证在 Telegram 已配置与未配置时的行为。[file: `bot.py`]
- Note: 如后续对命令轮询延迟更敏感，可考虑将 `DEFAULT_TIMEOUT` 与 `DEFAULT_LIMIT` 暴露为配置项（例如通过环境变量或 settings），以便在不同部署环境中调优。[file: `notifications/telegram_commands.py`]

