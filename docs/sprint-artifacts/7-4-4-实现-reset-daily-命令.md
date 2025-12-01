# Story 7.4.4: 实现 reset_daily 命令

Status: done

## Story

As a user,
I want to manually reset the daily loss baseline via a Telegram command,
so that I can safely resume trading after reviewing a large drawdown day and explicitly deciding to start a new risk window.

## Acceptance Criteria

1. **AC1 – /reset_daily 正确重置每日亏损基准（对齐 Epic 7.3 / 7.4.4，PRD FR12–FR18）**  
   - 在已正确配置 `TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID`，且 Bot 正常运行、风控系统启用（`RISK_CONTROL_ENABLED=true`）时：  
     - 当收到来自授权 Chat 的 `/reset_daily` 命令：  
       - 读取当前组合总权益（与 PRD、现有风控逻辑使用的 `total_equity` 定义严格一致）；  
       - 将 `RiskControlState.daily_start_equity` 更新为当前权益；  
       - 将 `RiskControlState.daily_start_date` 更新为当前 UTC 日期（`YYYY-MM-DD`）；  
       - 将 `RiskControlState.daily_loss_pct` 重置为 `0.0`；  
       - 将 `RiskControlState.daily_loss_triggered` 重置为 `False`；  
       - 整个操作是幂等的：对同一 UTC 日期、同一权益连续多次调用 `/reset_daily`，不会产生意外副作用。  

2. **AC2 – 与 Kill-Switch / 每日亏损限制的协同行为（对齐 Epic 7.3.3 / 7.4.2 / 7.4.4，PRD FR12–FR18）**  
   - 当每日亏损限制曾经触发、导致 `daily_loss_triggered=True` 且 Kill-Switch 已被激活时：  
     - `/reset_daily` 执行后：  
       - `daily_loss_triggered` 被重置为 `False`；  
       - 新的 `daily_start_equity` 记录为当前权益，`daily_loss_pct` 回到 `0.0`；  
       - **Kill-Switch 是否自动解除需在实现中作出明确决策并在文案中说明**：  
         - 推荐策略（与现有 `/resume` 语义保持一致）：保留 Kill-Switch 处于激活状态，但在确认消息中提示「基准已重置，可通过 `/resume confirm` 显式恢复交易」。  
     - 后续在发送 `/resume confirm` 时：  
       - 不再因为 `daily_loss_triggered` 阻塞恢复；  
       - 若实现选择在 `/reset_daily` 中自动解除 Kill-Switch，则需在本 Story 中显式说明风险并在文案中清晰提示。  
   - 当 Kill-Switch 是由手工 `/kill` 或 `KILL_SWITCH` 环境变量激活、而非每日亏损触发时：  
     - `/reset_daily` 只重置每日亏损基准字段，不改变 Kill-Switch 激活状态，也不影响后续 `/resume` 的二次确认语义。  

3. **AC3 – 用户反馈与文案（对齐 PRD「成功标准」「每日亏损限制」「Telegram 命令集成」）**  
   - `/reset_daily` 成功执行时，通过 Telegram 回复一条结构化 Markdown 文本，至少包含：  
     - 标题行：例如 `🧮 *每日亏损基准已重置*`；  
     - 新的当日起始权益：`daily_start_equity`，以美元金额格式展示（保留 2 位小数，与现有通知风格一致）；  
     - 当前亏损百分比重置结果（应为 `0.00%`）；  
     - 当前 Kill-Switch 状态与下一步建议，例如：  
       - Kill-Switch 仍然激活时：提示用户需要通过 `/resume confirm` 解除；  
       - 若实现选择自动解除 Kill-Switch，则需在文案中**醒目**标注「交易已恢复」并说明风险。  
   - 当风控系统未启用（`RISK_CONTROL_ENABLED=false`）或当前无法获取有效权益数据时：  
     - `/reset_daily` 不应静默失败，应返回一条降级提示（例如「风控系统未启用或当前权益不可用，无法重置每日基准」），并不修改任何 `RiskControlState` 字段。  

4. **AC4 – 安全性、健壮性与审计（对齐 PRD FR19–FR24, NFR3–NFR6）**  
   - 仅当命令来自配置的 `TELEGRAM_CHAT_ID` 时才执行 `/reset_daily`：  
     - 其它 Chat ID 的 `/reset_daily` 命令被静默丢弃，并记录 `WARNING` 级日志（沿用 7.4.1 行为）；  
   - `/reset_daily` 命令执行过程中：  
     - 任意异常（例如获取权益失败、状态对象为空等）不会中断 `_run_iteration()` 或破坏本地风控逻辑；  
     - 失败场景会记录 `ERROR` 级日志，并可向用户返回通用错误提示（不泄露内部细节）；  
   - 审计要求：  
     - 每次成功处理 `/reset_daily` 时，在日志中记录结构化信息（command、chat_id、old/new daily_start_equity、old/new daily_loss_pct、daily_loss_triggered 变化、kill_switch_active 状态等）；  
     - 可选地在 `ai_decisions.csv` 或等价审计通道中追加一条 `action="RISK_CONTROL"` 或 `DAILY_BASELINE_RESET` 的事件，用于后续回放与风控审计。  

5. **AC5 – 单元测试与回归（对齐 Epic 7.3 / 7.4.4，PRD 成功标准）**  
   - 在 `tests/test_notifications_telegram_commands.py` 与/或新的测试文件中新增测试用例，至少覆盖：  
     - 正常路径：在 `daily_loss_triggered=True` 与 Kill-Switch 激活的场景下执行 `/reset_daily`，验证基准字段更新、标志位重置与文案内容；  
     - 非每日亏损触发的 Kill-Switch 场景：验证 `/reset_daily` 不会误解除基于 `/kill` 或环境变量激活的 Kill-Switch；  
     - 风控未启用或权益不可用场景：验证命令行为为「不修改状态 + 友好降级提示」；  
     - 未授权 Chat ID：验证不会修改状态，且仅记录 WARNING 日志；  
     - 与 `/resume` 的协同：在 `/reset_daily` 后再执行 `/resume confirm`，验证能按预期解除因每日亏损触发的 Kill-Switch。  
   - 运行 `./scripts/run_tests.sh` 时，所有既有测试与本 Story 新增测试均通过。

## Tasks / Subtasks

- [x] **Task 1 – 设计 /reset_daily 命令语义与交互（AC1, AC2, AC3）**  
  - [x] 1.1 基于 `docs/epic-risk-control-enhancement.md` 与 PRD 明确 /reset_daily 在下列状态组合下的行为矩阵：  
        - Kill-Switch 未激活 / 已激活；  
        - 是否由每日亏损触发（`daily_loss_triggered`）；  
        - 风控系统是否启用（`RISK_CONTROL_ENABLED`）。  
  - [x] 1.2 最终确认是否在 `/reset_daily` 中自动解除由每日亏损触发的 Kill-Switch，还是保留 Kill-Switch 并仅解锁 `/resume confirm`；在 Dev Notes 中记录该设计决策与理由。  
  - [x] 1.3 设计 Telegram 回复文案模板（MarkdownV2），确保与现有风控通知和 `/status` 文案风格一致（中文 + emoji + 固定小数位）。

- [x] **Task 2 – 在风控核心中抽象每日基准重置 helper（AC1, AC2, AC4）**  
  - [x] 2.1 在 `core/risk_control.py` 中基于现有 `update_daily_baseline()` 与 `calculate_daily_loss_pct()` 设计一个专门用于「显式重置」的 helper（例如 `reset_daily_baseline(state, current_equity, *, reason)`），避免在命令层直接操作 dataclass 字段。  
  - [x] 2.2 确保该 helper 更新 `daily_start_equity`、`daily_start_date`、`daily_loss_pct`、`daily_loss_triggered`，并记录结构化日志（包含旧值与新值）。  
  - [x] 2.3 如决定在本 Story 中自动调整 Kill-Switch 状态，则在 helper 内通过 `deactivate_kill_switch()` 或等价 API 完成，并在日志中明确标注触发来源为 `telegram:/reset_daily`。

- [x] **Task 3 – 在 Telegram 命令层实现 /reset_daily（AC1–AC4）**  
  - [x] 3.1 在 `notifications/telegram_commands.py` 的命令处理工厂（例如 `create_kill_resume_handlers` 或扩展的 handler dict）中，为 `command == "reset_daily"` 添加 handler：  
        - 通过注入的 `total_equity_fn` 读取当前权益；  
        - 调用 Task 2 中新增的 helper 重置每日基准；  
        - 构造并发送 Telegram 回复消息。  
  - [x] 3.2 复用现有的 `_send_response()` 与 `_record_event()` 辅助函数，确保日志与审计事件风格与 `/kill`、`/resume`、`/status` 一致。  
  - [x] 3.3 在错误场景（权益不可用、helper 抛异常等）下，确保 handler 捕获异常、记录日志并返回合适的降级提示，而不是让异常冒泡到主循环。

- [x] **Task 4 – 测试与回归（AC5）**  
  - [x] 4.1 在 `tests/test_notifications_telegram_commands.py` 中新增针对 `/reset_daily` 的测试类：覆盖正常路径、未经授权 chat、风控关闭、权益不可用等典型场景。  
  - [x] 4.2 如新增 `reset_daily_baseline` 等 helper，在 `tests/test_core_risk_control.py` 或等价文件中添加对应单元测试，验证边界条件与日志行为。  
  - [x] 4.3 运行 `./scripts/run_tests.sh`，确保所有测试通过，并在 Change Log 中记录一次成功运行。  

## Dev Notes

### Requirements & Context Summary

- 本 Story 属于 **Epic 7.4: Telegram 命令集成** 的第四个实现 Story，对应 `sprint-status.yaml` 中的 key：`7-4-4-实现-reset-daily-命令`。  
- 需求主要来源：  
  - Epic 文档 `docs/epic-risk-control-enhancement.md` 中 **Story 7.4.4: 实现 /reset_daily 命令** 的拆解与示例代码：  
    - 明确 `/reset_daily` 需要重置 `daily_start_equity`、`daily_start_date`、`daily_loss_pct` 与 `daily_loss_triggered`，并在每日亏损限制触发后为用户提供「手动重开新一日风险窗口」的手段；  
    - 示例实现中给出了 `handle_reset_daily_command()` 的伪代码，需结合当前代码结构和 Kill-Switch 语义进行调整。[Source: docs/epic-risk-control-enhancement.md#Story-7.4.4-实现-reset_daily-命令]  
  - PRD 文档 `docs/prd-risk-control-enhancement.md` 中：  
    - **每日亏损限制功能** 小节（FR12–FR18）定义了 `daily_start_equity` / `daily_start_date` / `daily_loss_pct` 字段、触发逻辑以及 `/reset_daily` 的职责；  
    - **Telegram 命令集成** 小节（FR22–FR24）指出 `/reset_daily` 是一条敏感命令，需要与 `/kill`、`/resume`、`/status` 一起纳入统一的安全与审计框架。[Source: docs/prd-risk-control-enhancement.md#每日亏损限制功能]  
  - `docs/epics.md` 中 **Epic 7: 风控系统增强（Emergency Controls）** 与 **Epic 7.4: Telegram 命令集成（Post-MVP）** 的范围说明：  
    - Epic 7.3/7.4 一起为 Kill-Switch 与每日亏损限制提供「应急控制 + 远程命令」闭环；  
    - `/reset_daily` 是该闭环中「手动重置每日基准」的关键一环。[Source: docs/epics.md#Epic-7-风控系统增强-Emergency-Controls]  
- 与前序 Stories 的关系：  
  - Epic 7.1 / 7.3 已提供 `RiskControlState`、`update_daily_baseline()`、`calculate_daily_loss_pct()` 与 `check_daily_loss_limit()` 等核心能力，以及每日亏损限制触发 Kill-Switch 的逻辑（详见 `core/risk_control.py` 和 `docs/sprint-artifacts/7-3-1`–`7-3-4` 系列 Story）；  
  - Story 7.4.1 实现了 Telegram 命令接收与解析基础设施；Story 7.4.2 实现了 `/kill` 与 `/resume` 命令；Story 7.4.3 实现了 `/status` 命令并向用户暴露了当前每日亏损与阈值；  
  - 本 Story 在这些能力之上，为每日亏损限制补齐「手动重置」控制点，与 `/resume` 一起形成完整的恢复路径。  

### Architecture & Implementation Constraints

- **模块边界与职责：**  
  - `core/risk_control.py`：  
    - 继续作为所有风控状态变更的唯一入口：Kill-Switch 激活/解除、每日基准更新、每日亏损计算等；  
    - 本 Story 推荐在该模块中增加一个专门用于手动重置基准的 helper，以保证 Telegram 命令层不需要直接操作 dataclass 字段。  
  - `notifications/telegram_commands.py`：  
    - 已经提供 `TelegramCommand`、`TelegramCommandHandler`、`CommandResult`、`handle_kill_command()`、`handle_resume_command()`、`handle_status_command()` 以及 `create_kill_resume_handlers()`；  
    - 本 Story 需在同一模块中为 `reset_daily` 命令添加 handler，并在工厂函数中注册，保持命令分发逻辑集中且可测试。  
  - `bot.py`：  
    - 继续在 `_run_iteration()` 的早期阶段调用 `poll_telegram_commands()` 并通过中立入口 `process_telegram_commands()` / `create_kill_resume_handlers()` 处理命令；  
    - 不在主循环中直接拼装 `/reset_daily` 文案或操作风控状态。  

- **一致性与错误处理：**  
  - 错误处理与日志风格需延续 Story 7.4.1 / 7.4.2 / 7.4.3 中的约定：  
    - 使用统一的 WARNING/ERROR 文本前缀与字段顺序，便于集中 grep 与监控；  
    - 网络错误、权益获取失败、状态不一致等情况一律不应中断主循环。  
  - 权益获取逻辑应与现有 `/status` 命令中使用的 `total_equity_fn` 保持一致，避免出现两个定义不同的「当前权益」。  
  - 若决定在 `/reset_daily` 中自动解除由每日亏损触发的 Kill-Switch，必须在 Dev Notes 中记录该决策，并考虑：  
    - 与 `/resume confirm` 的职责边界；  
    - 与 PRD 中「敏感操作需要二次确认」的要求是否冲突。  

### Project Structure Notes

- 预期主要涉及文件（以实际实现为准）：  
  - `core/risk_control.py` —— 新增每日基准重置 helper，或在现有函数基础上封装出适合命令层调用的 API；  
  - `notifications/telegram_commands.py` —— 为 `reset_daily` 命令新增 handler，并在 `create_kill_resume_handlers()` 返回的 handlers dict 中注册；  
  - `bot.py` —— 如有需要，扩展命令处理装配逻辑以传入 `total_equity_fn`、`risk_control_enabled`、`daily_loss_limit_enabled` 等参数（复用 `/status` 路径的做法）；  
  - `tests/test_notifications_telegram_commands.py` —— 新增 `/reset_daily` 相关测试用例；  
  - （可选）`tests/test_core_risk_control.py` —— 新增针对每日基准重置 helper 的单元测试。  
- 实现需继续遵守 `docs/architecture/06-project-structure-and-mapping.md` 与 `docs/architecture/07-implementation-patterns.md` 中关于分层、日志与外部服务集成的约定。  

### Learnings from Previous Story

- **前一 Story:** 根据 `sprint-status.yaml` 的顺序，上一条已完成的 Story 是 `7-4-3-实现-status-命令`（状态为 `done`，详见 `docs/sprint-artifacts/7-4-3-实现-status-命令.md`）。  
- **可复用能力与约束：**  
  - `/status` 已经通过 `handle_status_command()` 和 `create_kill_resume_handlers()` 复用 `RiskControlState` 与 `total_equity_fn`，并以统一的 Markdown 模板向用户展示 `daily_loss_pct`、每日亏损阈值、起始权益与当前权益；  
  - 该 Story 在 Dev Notes 中强调 `/status` 作为「观察者」，只读风控状态而不修改，这一点在本 Story 中同样适用——/reset_daily 应通过清晰的 helper 修改状态，而不是在命令层做 ad-hoc 更新；  
  - 日志与审计字段格式（包括 `action="RISK_CONTROL_STATUS"` 等）已在 7.4.3 中建立，应在本 Story 中尽量复用，新增的 `DAILY_BASELINE_RESET` 事件应与现有事件一并纳入审计视角。  
- **对本 Story 的启示：**  
  - /reset_daily 是「改变状态」的命令，其风险高于 `/status`，需要更明确的文案提示与日志记录；  
  - 需要确保用户在收到「每日基准已重置」通知后，对 Kill-Switch 当前状态和下一步操作（继续暂停或恢复）有清晰预期，避免误以为系统已自动恢复交易；  
  - 与 `/resume` 的交互语义必须在文案与实现上保持一致，避免出现「文案建议 `reset_daily + resume`，但实际行为是 `reset_daily` 已直接恢复交易」这样的不一致。  

### References

- [Source: docs/epic-risk-control-enhancement.md#Story-7.4.4-实现-reset_daily-命令]  
- [Source: docs/prd-risk-control-enhancement.md#每日亏损限制功能]  
- [Source: docs/prd-risk-control-enhancement.md#Telegram-命令集成]  
- [Source: docs/epics.md#Epic-7.4-Telegram-命令集成-Post-MVP]  
- [Source: docs/sprint-artifacts/7-4-1-实现-telegram-命令接收机制.md]  
- [Source: docs/sprint-artifacts/7-4-2-实现-kill-和-resume-命令.md]  
- [Source: docs/sprint-artifacts/7-4-3-实现-status-命令.md]  
- [Source: docs/architecture/06-project-structure-and-mapping.md]  
- [Source: docs/architecture/07-implementation-patterns.md]

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/7-4-4-实现-reset-daily-命令.context.xml`（由后续 `story-context` 工作流生成后填充）  
- (相关) `docs/epic-risk-control-enhancement.md#Story-7.4.4-实现-reset_daily-命令`  
- (相关) `docs/prd-risk-control-enhancement.md#每日亏损限制功能`  

### Agent Model Used

- Cascade（本 Story 草稿由 SM/AI 协同创建，用于指导后续 Dev Story 实施与代码评审）

### Debug Log References

- `/reset_daily` 命令路径中的日志行为建议：  
  - 当成功重置每日基准时：记录 INFO 日志，包含旧/新 `daily_start_equity`、旧/新 `daily_loss_pct`、`daily_loss_triggered` 以及 Kill-Switch 状态；  
  - 当命令来自未授权 Chat 时：记录 WARNING 日志并忽略；  
  - 当获取权益失败、风控未启用或 helper 抛出异常时：记录 WARNING/ERROR 日志，并返回通用错误提示（如「暂时无法重置每日基准，请稍后重试」）。  

### Completion Notes List

- [x] 初始 Story 草稿已由 `/create-story` 工作流创建，等待后续 Dev Story 实施与代码评审。  
- [x] 完成实现后需更新本节，记录实际完成日期与 Definition of Done。

**设计决策记录 (Task 1.2):**
- `/reset_daily` **不会**自动解除 Kill-Switch，与 PRD 中「敏感操作需要二次确认」的要求保持一致
- 用户需要先执行 `/reset_daily` 重置每日基准，然后执行 `/resume confirm` 恢复交易
- 这样设计的理由：避免用户误操作导致在大亏损后立即恢复交易

**实现完成日期:** 2025-12-01

**Definition of Done:**
- ✅ AC1: `/reset_daily` 正确重置每日亏损基准（daily_start_equity, daily_start_date, daily_loss_pct, daily_loss_triggered）
- ✅ AC2: 与 Kill-Switch / 每日亏损限制协同行为正确（保留 Kill-Switch，清除 daily_loss_triggered）
- ✅ AC3: 用户反馈文案完整（MarkdownV2 格式，包含新旧权益、亏损百分比、Kill-Switch 状态提示）
- ✅ AC4: 安全性与审计（仅授权 Chat ID、结构化日志、异常处理）
- ✅ AC5: 单元测试覆盖所有场景，663 个测试全部通过  

### File List

- **已修改/新增的文件：**  
  - `core/risk_control.py` — 新增 `reset_daily_baseline()` helper 函数，用于手动重置每日亏损基准；  
  - `notifications/telegram_commands.py` — 新增 `handle_reset_daily_command()` 函数和 `reset_daily_handler`，并在 `create_kill_resume_handlers()` 中注册；  
  - `tests/test_notifications_telegram_commands.py` — 新增 `TestHandleResetDailyCommand` 和 `TestResetDailyHandlerIntegration` 测试类（约 40 个测试用例）；  
  - `tests/test_risk_control.py` — 新增 `TestResetDailyBaseline` 测试类（10 个测试用例）。  

## Change Log

- 2025-12-01: 初始 Story 草稿由 `/create-story` 工作流基于 PRD / Epic / 架构文档与前一 Story 7.4.3 生成，状态设为 `drafted`，等待后续 `story-context` 与 Dev Story 实施。
- 2025-12-01: 完成 `/reset_daily` 命令实现，包括：
  - 在 `core/risk_control.py` 中新增 `reset_daily_baseline()` helper
  - 在 `notifications/telegram_commands.py` 中新增 `handle_reset_daily_command()` 和 handler 注册
  - 新增约 50 个单元测试覆盖所有 AC 场景
  - 运行 `./scripts/run_tests.sh`，663 个测试全部通过
  - 状态更新为 `review`
- 2025-12-01: Senior Developer Review (AI) 完成，Outcome=Approve，Story 即将标记为 `done`

## Senior Developer Review (AI)

**Reviewer:** Nick  
**Date:** 2025-12-01  
**Outcome:** Approve

### Summary

- **实现与文案**：`/reset_daily` 通过 `reset_daily_baseline()` 在风控核心中重置每日基准字段，并在 Telegram 命令层返回结构化 MarkdownV2 文案，提示后续需显式 `/resume confirm` 才能恢复交易。  
- **Kill-Switch 协同**：重置仅清除每日亏损标志与基准，不自动解除 Kill-Switch；`/reset_daily` + `/resume confirm` 形成安全且可审计的恢复路径。  
- **测试与回归**：新增单元测试覆盖 AC1–AC5 描述的核心场景，`./scripts/run_tests.sh` 通过 663 个测试。  

### Key Findings

#### High Severity

- 无

#### Medium Severity

- 无

#### Low Severity / Advisory Notes

- 仅有少量风格与可扩展性建议（见文末 Action Items 中的 Advisory Notes），不影响当前 Story 的通过与上线安全性。

### Acceptance Criteria Coverage

| AC  | 描述（简要） | 状态 | 证据 |
| --- | ------------ | ---- | ---- |
| AC1 | `/reset_daily` 正确重置每日亏损基准（daily_start_equity / daily_start_date / daily_loss_pct / daily_loss_triggered），且同一日期同一权益重复调用无意外副作用 | IMPLEMENTED | 核心实现：`core/risk_control.py:537-608` 中 `reset_daily_baseline()` 完整更新 4 个字段并记录旧值/新值；命令层调用：`notifications/telegram_commands.py:739-887` 中 `handle_reset_daily_command()` 使用当前权益调用 helper 并回写状态；测试：`tests/test_risk_control.py:1342-1507`（`TestResetDailyBaseline.*`），`tests/test_notifications_telegram_commands.py:1368-1442`（`test_reset_daily_updates_baseline_fields`、`test_reset_daily_idempotent`）验证字段更新与幂等行为。 |
| AC2 | 与 Kill-Switch / 每日亏损限制协同：在每日亏损触发 Kill-Switch 时，`/reset_daily` 清除 `daily_loss_triggered` 和日亏百分比，但不自动解除 Kill-Switch；手工 `/kill` 或 env 激活的 Kill-Switch 不受影响；`/reset_daily` 之后 `/resume confirm` 可按预期解除 Kill-Switch | IMPLEMENTED | helper 不修改 Kill-Switch 字段：`core/risk_control.py:537-608` 仅变更每日基准相关字段；命令层在基于 `kill_switch_active` 构造文案但不修改其状态：`notifications/telegram_commands.py:819-857`；测试：`tests/test_notifications_telegram_commands.py:1447-1540`（`test_reset_daily_clears_daily_loss_triggered`、`test_reset_daily_preserves_kill_switch_active`、`test_reset_daily_does_not_affect_manual_kill_switch`）以及集成测试 `test_reset_daily_then_resume_flow`（`tests/test_notifications_telegram_commands.py:1760-1803`）验证 `/reset_daily` 清除日亏标志后，`/resume confirm` 可以成功解除 Kill-Switch。 |
| AC3 | 用户反馈与文案：成功路径展示「每日亏损基准已重置」、新旧起始权益、当前亏损重置为 0.00%、原亏损百分比；根据 Kill-Switch 状态提示「需要 `/resume confirm`」或「交易功能正常运行中」。风控未启用或权益不可用时返回明确降级提示且不改状态 | IMPLEMENTED | 成功路径文案构造：`notifications/telegram_commands.py:842-867`，包含标题、金额格式化、`0\.00%` 亏损以及 Kill-Switch 提示段（`Kill\-Switch 仍处于激活状态` / `交易功能正常运行中`）；降级场景：`notifications/telegram_commands.py:782-817` 中 risk_control_disabled 与 equity unavailable 分支返回友好提示且 `state_changed=False`；测试：`tests/test_notifications_telegram_commands.py:1392-1412`（`test_reset_daily_returns_confirmation_message`）、`1550-1603`（`test_reset_daily_risk_control_disabled`、`test_reset_daily_equity_unavailable`、`test_reset_daily_equity_nan`）验证文案内容与不修改状态。 |
| AC4 | 安全性、健壮性与审计：仅授权 Chat ID 的命令会被处理；异常不会中断主循环；为 `/reset_daily` 和 helper 记录结构化日志，并通过审计事件记录 `DAILY_BASELINE_RESET` | IMPLEMENTED | 授权 Chat 过滤在通用命令接收层：`notifications/telegram_commands.py` 中 `TelegramCommandHandler.poll_commands()` 已有基于 `allowed_chat_id` 的过滤与 WARNING 日志（对应测试 `TestChatIdFiltering.*`），`/reset_daily` 复用同一路径；helper 审计日志：`core/risk_control.py:590-606` 以结构化信息记录原因、旧/新 daily_start_equity、daily_loss_pct、daily_loss_triggered 与 Kill-Switch 状态；命令层日志：`notifications/telegram_commands.py:775-780`（接收日志）、`870-880`（状态变更摘要）；审计事件：`create_kill_resume_handlers` 中 `reset_daily_handler` 调用 `_record_event` 记录 `DAILY_BASELINE_RESET`（`notifications/telegram_commands.py:1019-1051`）；测试：`tests/test_notifications_telegram_commands.py:1609-1661` 和 `tests/test_risk_control.py:1419-1461` 验证日志内容与事件记录。 |
| AC5 | 单元测试与回归：为 `/reset_daily` 命令与 `reset_daily_baseline` helper 新增单元测试，覆盖正常路径、Kill-Switch 协同、风控关闭/权益不可用、`/reset_daily` + `/resume confirm` 流程，以及日志与审计事件；全量测试通过 | IMPLEMENTED | `/reset_daily` 命令测试：`tests/test_notifications_telegram_commands.py:1311-1661`（`TestHandleResetDailyCommand` 覆盖正常路径、Kill-Switch 场景、降级场景、日志场景）；集成测试：`TestResetDailyHandlerIntegration`（`tests/test_notifications_telegram_commands.py:1664-1843`）覆盖 handler 注册、状态修改、消息发送与事件记录、`reset_daily` + `resume confirm` 流；helper 测试：`tests/test_risk_control.py:1342-1507`（`TestResetDailyBaseline` 全面覆盖字段更新、Kill-Switch 保持、日志与边界值）；回归：`./scripts/run_tests.sh` 执行结果为 663 passed。 |

**AC 覆盖总结：** 5/5 条验收标准均已实现并有对应测试与日志证据，未发现缺失或部分实现的 AC。

### Task Completion Validation

| Task | Marked As | Verified As | Evidence |
| ---- | --------- | ----------- | -------- |
| Task 1 – 设计 /reset_daily 命令语义与交互 | Completed | VERIFIED COMPLETE | Story Dev Notes 中的设计决策记录及行为矩阵分析：`docs/sprint-artifacts/7-4-4-实现-reset-daily-命令.md:96-156`；实现与测试中体现 Kill-Switch 交互与文案设计：`notifications/telegram_commands.py:739-887`，`tests/test_notifications_telegram_commands.py:1368-1501`。 |
| 1.1 行为矩阵（Kill-Switch 状态 / daily_loss_triggered / RISK_CONTROL_ENABLED） | Completed | VERIFIED COMPLETE | 不同组合通过测试覆盖：正常场景、日亏触发 + Kill-Switch 激活、手工 Kill-Switch、风控关闭、权益不可用等；见 `tests/test_notifications_telegram_commands.py:1368-1603` 与 `TestResetDailyHandlerIntegration`。 |
| 1.2 是否自动解除 Kill-Switch 决策 | Completed | VERIFIED COMPLETE | helper 明确不解除 Kill-Switch：`core/risk_control.py:557-559`；命令层保留 Kill-Switch 状态并通过文案提示需 `/resume confirm`：`notifications/telegram_commands.py:850-857`；设计决策在 Completion Notes 中记录：`docs/sprint-artifacts/7-4-4-实现-reset-daily-命令.md:194-207`。 |
| 1.3 Telegram 回复文案模板（MarkdownV2） | Completed | VERIFIED COMPLETE | 文案实现与转义：`notifications/telegram_commands.py:842-867`；MarkdownV2 细节（金额格式化和转义）与测试断言：`tests/test_notifications_telegram_commands.py:1392-1412`。 |
| Task 2 – 在风控核心中抽象每日基准重置 helper | Completed | VERIFIED COMPLETE | `reset_daily_baseline()` 实现：`core/risk_control.py:537-608`；日志与字段更新行为通过 `TestResetDailyBaseline` 全面验证：`tests/test_risk_control.py:1342-1507`。 |
| 2.1 基于现有 helper 设计显式重置 helper | Completed | VERIFIED COMPLETE | 新增 helper 复用现有模式（使用 `replace` 返回新 state，保留 Kill-Switch 字段）：`core/risk_control.py:537-588`。 |
| 2.2 更新 4 个每日基准字段并记录结构化日志 | Completed | VERIFIED COMPLETE | 字段更新：`core/risk_control.py:582-587`；结构化日志：`core/risk_control.py:590-606`；测试验证日志内容：`tests/test_risk_control.py:1419-1461`。 |
| 2.3 （可选）helper 内自动调整 Kill-Switch | Completed | VERIFIED COMPLETE (by design: not auto-deactivating) | 本 Story 根据 PRD 要求选择 **不在 helper 中自动解除 Kill-Switch**，而是在 Dev Notes 中记录该决策（`docs/sprint-artifacts/7-4-4-实现-reset-daily-命令.md:194-207`），并通过 `/resume confirm` 路径统一处理 Kill-Switch 解除。 |
| Task 3 – 在 Telegram 命令层实现 /reset_daily | Completed | VERIFIED COMPLETE | 命令 handler 与工厂集成：`notifications/telegram_commands.py:739-887` 中 `handle_reset_daily_command()`，以及 `create_kill_resume_handlers()` 内部 `reset_daily_handler` 定义与注册（`notifications/telegram_commands.py:1019-1053`）；集成测试：`tests/test_notifications_telegram_commands.py:1664-1803`。 |
| 3.1 在 handlers 工厂中为 reset_daily 添加 handler | Completed | VERIFIED COMPLETE | handler 实现与注册：`notifications/telegram_commands.py:1019-1053`；集成测试 `test_reset_daily_handler_registered` 和 `test_reset_daily_handler_modifies_state` 验证 handlers dict 中存在 `reset_daily` 且正确修改状态：`tests/test_notifications_telegram_commands.py:1667-1710`。 |
| 3.2 复用 `_send_response()` 与 `_record_event()` | Completed | VERIFIED COMPLETE | `reset_daily_handler` 使用 `_send_response` 发送 MarkdownV2 文本并通过 `_record_event` 记录 `DAILY_BASELINE_RESET` 事件：`notifications/telegram_commands.py:1019-1051`；测试 `test_reset_daily_handler_sends_message_and_records_event` 验证消息与事件：`tests/test_notifications_telegram_commands.py:1712-1758`。 |
| 3.3 错误场景下捕获异常并返回降级提示 | Completed | VERIFIED COMPLETE | `reset_daily_handler` 在 try/except 中捕获异常并发送降级消息：`notifications/telegram_commands.py:1026-1041`；测试 `test_reset_daily_handler_catches_exceptions` 验证异常捕获、降级文案与 ERROR 日志：`tests/test_notifications_telegram_commands.py:1805-1842`。 |
| Task 4 – 测试与回归 | Completed | VERIFIED COMPLETE | 新增 `/reset_daily` 命令与 helper 的单元测试，且全量测试通过：`tests/test_notifications_telegram_commands.py:1311-1842`，`tests/test_risk_control.py:1342-1507`，以及 `./scripts/run_tests.sh` 执行日志（663 passed）。 |
| 4.1 `/reset_daily` 命令测试类 | Completed | VERIFIED COMPLETE | `TestHandleResetDailyCommand` 与 `TestResetDailyHandlerIntegration` 覆盖正常路径、Kill-Switch 协同、降级场景和 `/reset_daily` + `/resume confirm` 流：`tests/test_notifications_telegram_commands.py:1311-1842`。未单独为未授权 Chat 的 `/reset_daily` 编写测试，但该场景由已有的 `TestChatIdFiltering` 用例在命令接收层对所有命令统一覆盖。 |
| 4.2 helper 测试 | Completed | VERIFIED COMPLETE | `TestResetDailyBaseline` 系列用例覆盖字段更新、Kill-Switch 保持、日志内容以及多种边界值：`tests/test_risk_control.py:1342-1507`。 |
| 4.3 全量测试与回归 | Completed | VERIFIED COMPLETE | `./scripts/run_tests.sh` 成功运行，输出 `663 passed`，覆盖本 Story 新增的所有测试用例。 |

**Tasks 总结：** 所有标记为 Completed 的任务与子任务均在代码与测试中找到对应实现或设计记录，未发现「标记完成但实际上未做」的情况。

### Test Coverage and Gaps

- `/reset_daily` 的正常路径、各种 Kill-Switch 与 daily_loss_triggered 组合、风控关闭/权益不可用、异常路径以及与 `/resume confirm` 的联动均有清晰的单元 & 集成测试覆盖。  
- helper `reset_daily_baseline()` 拥有专门的测试类，覆盖正常场景和边界条件（None/0/负权益），并验证日志内容。  
- 未授权 Chat ID 场景通过通用的 `TestChatIdFiltering` 覆盖所有命令类型，包括未来扩展的 `/reset_daily`，无需为该命令重复相同逻辑测试。  

### Architectural Alignment

- **分层与职责**：每日基准重置逻辑集中在 `core/risk_control.py`，Telegram 命令层只通过 helper 和 `CommandResult` 进行交互，保持了良好的分层与可测试性。  
- **依赖注入**：`create_kill_resume_handlers()` 通过注入 `total_equity_fn`、`positions_count_fn`、`send_fn`、`record_event_fn` 等依赖，`/reset_daily` handler 复用同一工厂，和既有 `/kill`、`/resume`、`/status` 一致。  
- **日志与审计**：日志格式与 7.4.1–7.4.3 保持一致，审计事件 `DAILY_BASELINE_RESET` 与 `RISK_CONTROL_STATUS` 共享相同的事件记录通道。整体与现有架构文档中关于风控与通知模块的约束相符。  

### Security Notes

- `/reset_daily` 命令只会在通过 `TelegramCommandHandler` 过滤后的授权 Chat ID 上执行；未授权 Chat 的命令在统一接收层被丢弃并记录 WARNING 日志。  
- handler 在获取权益或调用 helper 失败时会捕获异常并返回通用错误消息，避免泄露内部细节，并通过 ERROR 日志保留排障线索。  
- 未引入新的外部依赖或敏感配置，继续复用已有的 Telegram 与风控配置机制。  

### Best-Practices and References

- 代码实现遵循 `docs/architecture/06-project-structure-and-mapping.md` 与 `07-implementation-patterns.md` 中的分层、日志与依赖注入约定。  
- `/reset_daily` 的安全语义（不自动解除 Kill-Switch、需要显式 `/resume confirm`）符合 PRD 中「敏感操作需要二次确认」的原则。  

### Action Items

**Code Changes Required:**

- 无（当前实现满足 Story 所有验收标准和任务要求，可直接将 Story 标记为 done）。

**Advisory Notes:**

- Note: 如未来需要对 `handle_reset_daily_command` 注入自定义 `reset_fn`，建议确保其签名与 `reset_daily_baseline(state, current_equity, reason=...)` 保持一致，并在文档中明确说明，以避免误用（当前代码路径未对外暴露该扩展点，属于低风险建议）。  
- Note: 如希望在测试层面与 AC5 的用例列表做到 1:1 映射，可以额外添加一个「未授权 Chat 发送 `/reset_daily`」的集成测试，用例结构可复用现有的 `TestChatIdFiltering`，本条为重复验证，属于非必需增强。
