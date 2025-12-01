# Story 7.4.5: 实现 help 命令和安全校验

Status: done

## Story

As a user,
I want a clear `/help` command and secure handling of all Telegram commands,
so that I always know what I can do and the trading bot is protected from unauthorized or malformed requests.

## Acceptance Criteria

1. **AC1 – /help 返回完整且可扩展的命令帮助列表（对齐 PRD FR22、FR24）**  
   - 在已正确配置 `TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID`，且 Bot 正常运行时：  
     - 当授权 Chat 发送 `/help` 命令时：  
       - 返回一条结构化 Markdown 文本，至少包含以下命令及简要说明：  
         - `/kill` – 激活 Kill-Switch，暂停所有新开仓；  
         - `/resume confirm` – 解除 Kill-Switch（带二次确认语义）；  
         - `/status` – 查看当前风控状态与每日亏损信息；  
         - `/reset_daily` – 手动重置每日亏损基准；  
         - `/help` – 显示帮助信息本身；  
       - 文案与 `docs/prd-risk-control-enhancement.md` 中的命令列表语义保持一致，且便于未来扩展更多命令。  
   - 帮助信息在风险控制关闭（`RISK_CONTROL_ENABLED=false`）时仍然可以安全返回（可以在文案中提示当前风控已关闭）。

2. **AC2 – 仅处理来自授权 Chat 的命令（对齐 PRD FR23、Epic 7.4.5 安全校验）**  
   - 所有命令（包括 `/help`）必须通过统一的命令接收层验证 `chat_id == TELEGRAM_CHAT_ID`：  
     - 当命令来自授权 Chat：按照既有逻辑继续分发到各 handler；  
     - 当命令来自未授权 Chat：  
       - 当前 Story 不返回任何用户可见响应（静默忽略或返回通用错误均可，但不得暴露敏感信息）；  
       - 记录一条 `WARNING` 级别日志，包含 `command` 与 `chat_id`，沿用 7-4-1 的日志格式。  
   - 安全校验逻辑集中在 `notifications/telegram_commands.py` / `TelegramCommandHandler` 路径中，而不是在各 handler 内重复实现。

3. **AC3 – 未知命令统一回退到帮助信息且不中断主循环（对齐 PRD FR24）**  
   - 当授权 Chat 发送未知命令（既不是 `/kill`、`/resume`、`/status`、`/reset_daily`、`/help`）：  
     - 命令处理结果返回一条「未知命令」提示，并附上与 `/help` 一致或子集的命令列表；  
     - 不修改任何 `RiskControlState` 字段，不影响当前 Kill-Switch / 每日亏损状态；  
     - 记录一条 `INFO` 或 `WARNING` 日志，说明收到未知命令并已回退到帮助信息。  
   - 无论命令是否合法或是否被识别，命令处理异常都不会中断 `_run_iteration()` 主循环。异常需被捕获并记录 `ERROR` 日志。

4. **AC4 – 单元测试与回归（对齐 Epic 7.4.5 与 PRD 成功标准）**  
   - 在 `tests/test_notifications_telegram_commands.py` 或等价文件中新增测试用例，至少覆盖：  
     - 授权 Chat 发送 `/help`：验证文案内容与命令列表；  
     - 未授权 Chat 发送 `/help`：验证不会返回响应，且有 WARNING 日志；  
     - 授权 Chat 发送未知命令：验证返回「未知命令 + 帮助」信息且不修改风险控制状态；  
     - 命令处理过程中抛出异常时：验证异常被捕获、用户收到通用错误提示（可选）且主循环不被中断。  
   - 运行 `./scripts/run_tests.sh` 时，所有既有测试与本 Story 新增测试均通过。

## Tasks / Subtasks

- [x] **Task 1 – 设计 /help 文案与可扩展结构（AC1, AC3）**  
  - [x] 1.1 基于 `docs/epic-risk-control-enhancement.md` 与 `docs/prd-risk-control-enhancement.md`，列出所有当前支持的 Telegram 风控命令及其语义。  
  - [x] 1.2 设计 `HELP_MESSAGE` 文案（MarkdownV2 友好），确保：命令清单清晰、与 PRD 中的命令说明一致、未来可无痛追加新命令。  
  - [x] 1.3 确认在风控关闭或部分功能禁用时，帮助文案的语气与提示方式（例如在文案末尾追加一行状态提示）。

- [x] **Task 2 – 梳理安全校验与命令分发路径（AC2, AC3）**  
  - [x] 2.1 复查 Story 7.4.1 中的命令接收与 `chat_id` 过滤逻辑，确认安全校验的“唯一入口”位置。  
  - [x] 2.2 如有必要，在 `TelegramCommandHandler` 或等价工厂中集中实现 `chat_id` 校验，确保包括 `/help` 在内的所有命令都统一走这一逻辑。  
  - [x] 2.3 定义未知命令的处理策略（返回帮助信息 / 简短错误 + 帮助链接），并确保不会修改任何风控状态。  

- [x] **Task 3 – 实现 /help handler 与未知命令处理（AC1–AC3）**  
  - [x] 3.1 在 `notifications/telegram_commands.py` 中新增 `handle_help_command()` 或等价函数，复用现有 `CommandResult` / `_send_response()` / `_record_event()` 模式。  
  - [x] 3.2 在命令 handler 工厂（例如 `create_kill_resume_handlers` 或扩展版命令映射）中注册 `help` handler，保持与 `/kill`、`/resume`、`/status`、`/reset_daily` 一致的结构。  
  - [x] 3.3 在命令分发逻辑中为未知命令添加统一 fallback：构造「未知命令」提示并附带帮助列表。  
  - [x] 3.4 确保所有路径下异常被捕获并记录日志，不会让异常冒泡到主循环。  

- [x] **Task 4 – 测试与回归（AC4）**  
  - [x] 4.1 在 `tests/test_notifications_telegram_commands.py` 中新增针对 `/help` 与未知命令的测试用例，覆盖授权/未授权 Chat、正常/异常路径。  
  - [x] 4.2 如有通用命令接收类（例如 `TelegramCommandHandler`），为其安全校验与未知命令逻辑添加/补充单元测试。  
  - [x] 4.3 运行 `./scripts/run_tests.sh`，确保所有测试通过，并在 Change Log 中记录一次成功运行。  

## Dev Notes

### Requirements & Context Summary

- 本 Story 属于 **Epic 7.4: Telegram 命令集成（Post-MVP）** 的第五个实现 Story，对应 `sprint-status.yaml` 中的 key：`7-4-5-实现-help-命令和安全校验`。  
- 需求主要来源：  
  - Epic 文档 `docs/epic-risk-control-enhancement.md` 中 **Story 7.4.5: 实现 /help 命令和安全校验**：  
    - 明确 `/help` 需要返回所有可用命令的帮助信息；  
    - 要求**仅**处理来自配置的 `TELEGRAM_CHAT_ID` 的命令，对其它 Chat ID 的命令进行安全忽略并记录日志；  
    - 未知命令应回退到帮助信息，避免用户陷入“无反馈”状态。[Source: docs/epic-risk-control-enhancement.md#Story-7.4.5-实现-help-命令和安全校验]  
  - 风控 PRD 文档 `docs/prd-risk-control-enhancement.md` 中「Telegram 命令集成」与「日志与审计」章节：  
    - **FR22–FR24** 定义了通过 Telegram 接收命令、只接受 `TELEGRAM_CHAT_ID`、未知命令返回帮助信息的需求；  
    - 命令列表中包含 `/kill`、`/resume`、`/status`、`/reset_daily`、`/help` 五条核心命令。[Source: docs/prd-risk-control-enhancement.md#Telegram-命令集成]  
  - `docs/epics.md` 中 **Epic 7: 风控系统增强（Emergency Controls）** 与 **Epic 7.4: Telegram 命令集成** 的范围说明：  
    - Telegram 命令集成是风控系统的操控界面；  
    - `/help` 是用户发现与理解其它风控命令（特别是 `/kill` / `/resume` / `/reset_daily`）的关键入口。[Source: docs/epics.md#Epic-7.4-Telegram-命令集成-Post-MVP]

### Architecture & Implementation Constraints

- **模块边界与职责：**  
  - `notifications/telegram.py`：负责底层 Telegram Bot API 调用与消息发送；  
  - `notifications/telegram_commands.py`：集中实现命令解析、命令 handler 与命令分发，是本 Story 的核心改动位置；  
  - `bot.py`：通过统一入口轮询或接收 Telegram 命令，然后委托给命令处理模块，不直接处理 `/help` 文案或安全逻辑。  
- **项目结构约束（参考 `docs/architecture/06-project-structure-and-mapping.md`）：**  
  - 所有 Telegram 相关逻辑应位于 `notifications/` 层，不应泄漏到 `core/` 或 `strategy/`；  
  - 命令 handler 使用纯函数 + 明确依赖注入（如 `send_fn`、`record_event_fn`、`total_equity_fn`），便于单元测试。  
- **实现模式约束（参考 `docs/architecture/07-implementation-patterns.md`）：**  
  - 遵循现有命名与错误处理模式：函数使用 `snake_case`，日志采用统一格式与前缀；  
  - 所有外部调用（Telegram API）应通过集中封装，避免在多个模块中重复拼接 HTTP 请求。  

### Project Structure Notes

- 预计主要涉及文件（以实际实现为准）：  
  - `notifications/telegram_commands.py` —— 新增 `/help` 命令 handler、未知命令 fallback 逻辑，以及与现有命令共享的安全校验与命令映射；  
  - `notifications/telegram.py` —— 如需扩展发送辅助函数或统一 MarkdownV2 转义，可在此补充；  
  - `bot.py` —— 仅在需要时微调命令处理装配逻辑，保持「统一从命令处理模块获取 handler」的模式；  
  - `tests/test_notifications_telegram_commands.py` —— 新增 `/help` 与未知命令的测试类与测试用例。
- 实现应继续遵守现有关于「运行时数据目录」「配置通过 .env 注入」「测试全部集中在 tests/ 目录」的约定。

### Learnings from Previous Story

- **前一 Story:** 根据 `sprint-status.yaml` 的顺序，上一条 Story 是 `7-4-4-实现-reset-daily-命令`（当前状态为 `done`，详见 `docs/sprint-artifacts/7-4-4-实现-reset-daily-命令.md`）。  
- **可复用能力与约束：**  
  - Story 7.4.4 已在 `core/risk_control.py` 中实现 `reset_daily_baseline()` helper，并在 `notifications/telegram_commands.py` 中新增 `handle_reset_daily_command()` 及对应 handler：  
    - 统一通过 `CommandResult` 返回消息文本与状态变更标志；  
    - 使用 `_send_response()` 和 `_record_event()` 写入 Telegram 与审计事件；  
    - 在异常场景下捕获错误并记录结构化日志，而非让异常冒泡到主循环。  
  - 现有 7.4.x 系列 Story（特别是 7.4.1 / 7.4.2 / 7.4.3 / 7.4.4）已经建立了如下模式：  
    - 所有命令共享统一命令接收与 `chat_id` 过滤路径；  
    - 命令 handler 采用注入依赖的方式构造，便于在测试中替换 `send_fn` / `record_event_fn`；  
    - 日志与审计事件字段结构保持一致，便于后续回放与监控。  
- **对本 Story 的启示：**  
  - `/help` 与未知命令的处理应完全复用现有命令分发与安全校验路径，而不是新增一套并行机制；  
  - 帮助文案中列出的命令需要与已实现的 handler 保持同步，建议从统一的「命令注册表」或配置结构生成，减少文案与实现脱节的风险；  
  - 日志与审计建议继续沿用 7.4.4 中的模式，例如为 `/help` 或未知命令访问增加轻量级审计事件（可选），便于后续分析用户交互习惯。

### References

- [Source: docs/epic-risk-control-enhancement.md#Story-7.4.5-实现-help-命令和安全校验]  
- [Source: docs/prd-risk-control-enhancement.md#Telegram-命令集成]  
- [Source: docs/prd-risk-control-enhancement.md#日志与审计]  
- [Source: docs/epics.md#Epic-7-风控系统增强-Emergency-Controls]  
- [Source: docs/epics.md#Epic-7.4-Telegram-命令集成-Post-MVP]  
- [Source: docs/sprint-artifacts/7-4-1-实现-telegram-命令接收机制.md]  
- [Source: docs/sprint-artifacts/7-4-2-实现-kill-和-resume-命令.md]  
- [Source: docs/sprint-artifacts/7-4-3-实现-status-命令.md]  
- [Source: docs/sprint-artifacts/7-4-4-实现-reset-daily-命令.md]  
- [Source: docs/architecture/06-project-structure-and-mapping.md]  
- [Source: docs/architecture/07-implementation-patterns.md]

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/7-4-5-实现-help-命令和安全校验.context.xml`（预计由后续 `story-context` 工作流生成后填充）  
- (相关) `docs/epic-risk-control-enhancement.md#Story-7.4.5-实现-help-命令和安全校验`  
- (相关) `docs/prd-risk-control-enhancement.md#Telegram-命令集成`

### Agent Model Used

- Cascade（本 Story 草稿由 SM/AI 协同创建，用于指导后续 Dev Story 实施与代码评审）

### Debug Log References

- 对 `/help` 与未知命令的日志建议：  
  - 收到授权 Chat 的命令时记录 `INFO` 日志，包含 `command`、`chat_id` 与解析结果；  
  - 收到未授权 Chat 的命令时记录 `WARNING` 日志（不返回任何敏感信息给用户）；  
  - 对未知命令记录 `INFO` / `WARNING` 日志并标注已回退到帮助信息；  
  - 对异常路径记录 `ERROR` 日志，并确保异常不会中断主循环。  

### Completion Notes List

- [x] 初始 Story 草稿已由 `/create-story` 工作流创建。  
- [x] 实现完成日期：2025-12-01
- [x] 实现内容：
  - 添加 `COMMAND_REGISTRY` 命令注册表，支持可扩展的命令列表
  - 添加 `_build_help_message()` 函数生成帮助文案
  - 添加 `handle_help_command()` 处理 /help 命令
  - 添加 `handle_unknown_command()` 处理未知命令
  - 更新 `process_telegram_commands()` 支持 `__unknown__` handler
  - 在 `create_kill_resume_handlers()` 中注册 help 和 unknown handlers
  - 新增 17 个测试用例覆盖所有 AC

### Completion Notes
**Completed:** 2025-12-01  
**Definition of Done:** All acceptance criteria met, code reviewed, tests passing  

### File List

- **MODIFIED** `notifications/telegram_commands.py` — 新增 /help 和未知命令处理逻辑
- **MODIFIED** `tests/test_notifications_telegram_commands.py` — 新增 Story 7.4.5 测试用例  

## Change Log

- 2025-12-01: 初始 Story 草稿由 `/create-story` 工作流基于 PRD / Epic / 架构文档与前一 Story 7.4.4 生成，状态设为 `drafted`，等待后续 `story-context` 与 Dev Story 实施。
- 2025-12-01: Story 实现完成。新增 `handle_help_command()` 和 `handle_unknown_command()` 函数，更新 `process_telegram_commands()` 支持未知命令 fallback，在 `create_kill_resume_handlers()` 中注册 help 和 unknown handlers。新增 17 个测试用例，所有 678 个测试通过。状态更新为 `review`。
