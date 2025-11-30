# Story 7.2.5: 实现 Kill-Switch 状态变更通知

Status: done

## Story

As a user,
I want to receive Telegram notifications when Kill-Switch status changes,
so that I'm aware of risk control events and can react quickly to risk control actions.

## Acceptance Criteria

1. **AC1 – Kill-Switch 激活时发送结构化通知（PRD FR11, FR19 对齐）**  
   - 当 Kill-Switch 状态从 **未激活 → 激活** 时（无论来源是环境变量、每日亏损限制、Telegram 命令等）：  
     - 系统发送一条 Telegram 通知，仅在状态实际发生变更时触发（去重/防抖）。  
     - 通知正文至少包含以下信息：  
       - 触发原因（例如：手动触发 / 每日亏损限制 / 环境变量 / 其他）；  
       - 触发时间（统一使用 UTC ISO8601，例如 `2025-11-30T12:34:56Z`）；  
       - 当前持仓数量（总持仓数，便于评估风险敞口）；  
       - 恢复交易的推荐指令提示（例如：`/resume confirm` 或等价文案）。  
     - 当 Telegram 相关配置（bot token / chat id）缺失时：  
       - 不抛出异常，不影响主循环执行；  
       - 在日志中记录一条 INFO/WARNING，说明「因未配置 Telegram，跳过 Kill-Switch 通知」。

2. **AC2 – Kill-Switch 解除时发送确认通知（PRD FR11 对齐）**  
   - 当 Kill-Switch 状态从 **激活 → 未激活** 时：  
     - 系统发送一条 Telegram 通知，仅在状态实际发生变更时触发。  
     - 通知正文至少包含：  
       - 已解除 Kill-Switch 的明确提示；  
       - 当前时间（UTC ISO8601）；  
       - 简要说明解除原因或路径（例如：`/resume confirm`、每日亏损手动重置等）。  
     - Kill-Switch 保持未激活状态下重复调用「解除」逻辑时，不应重复发送通知（保持幂等）。

3. **AC3 – 通知内容符合 Telegram Markdown 规范且与现有模块对齐**  
   - Kill-Switch 通知使用 Markdown 风格排版，遵循现有 `notifications/telegram.py` 中 `send_telegram_message` 的使用模式：  
     - 使用适度的 emoji（例如 `🚨` / `✅`）和粗体标题提高可读性；  
     - 文本在必要位置进行转义，避免触发 Telegram 的 `can't parse entities` 报错；  
     - 如被 Telegram 返回 400 且为 Markdown 解析错误，沿用现有降级策略（去掉 parse_mode 或去除 ANSI 颜色代码）重试。  
   - 消息构建逻辑与发送逻辑解耦：  
     - 建议在单独的 helper（例如 `notify_kill_switch_activated(...)` / `notify_kill_switch_deactivated(...)`）中组装消息文本；  
     - 实际发送通过注入的 `send_fn` 或复用 `send_telegram_message`，方便在单元测试中 stub/mock。

4. **AC4 – 日志与测试覆盖（与 FR19/FR20、一致性要求对齐）**  
   - 日志：  
     - Kill-Switch 状态每次发生变更时，在日志中记录一条结构化记录（INFO 或 WARNING），包含：  
       - `old_state` / `new_state`、`reason`、`positions_count` 等关键字段；  
       - 若因 Telegram 配置缺失而未能发送通知，同样在日志中给出说明。  
   - 测试：  
     - 至少为通知构建与发送路径新增 3–4 个单元测试，覆盖：  
       - 激活通知消息内容与字段正确；  
       - 解除通知消息内容与字段正确；  
       - Telegram 配置缺失时静默跳过但记录日志；  
       - 重复激活/解除不重复发送（幂等性）。  
     - 如引入新的辅助函数或模块（例如专门的通知 helper），需为其核心逻辑提供直接单元测试；  
     - `./scripts/run_tests.sh` 全量测试应继续通过。

## Tasks / Subtasks

- [x] **Task 1 – 设计 Kill-Switch 通知 API（AC1, AC2, AC3）**  
  - [x] 1.1 复查 `core/risk_control.py` 中 Kill-Switch 生命周期（`activate_kill_switch` / `deactivate_kill_switch` 等）以及调用点，确定挂接通知的单一入口。  
  - [x] 1.2 设计并实现 Kill-Switch 通知 helper（例如放在 `notifications/telegram.py` 或新的 `notifications/risk_control_notifications.py` 中）：  
        - 提供 `notify_kill_switch_activated(reason: str, positions_count: int, ...)` 与 `notify_kill_switch_deactivated(..., ...)` 等函数；  
        - 内部组装 Markdown 文本，外部通过注入 send 函数或配置调用 `send_telegram_message(...)`。  
  - [x] 1.3 明确从何处获取 `bot_token` / `chat_id` / 关注的持仓数量等信息（对应模块可能是 `config/settings.py`、`notifications/telegram.py`、`core/state.py` 等），在 Dev Notes 中记录最终决策。

- [x] **Task 2 – 集成通知到 Kill-Switch 状态变更路径（AC1, AC2, AC4）**  
  - [x] 2.1 在 Kill-Switch 激活/解除逻辑中调用通知 helper，并确保仅在状态真正发生变化时触发（例如通过比较旧状态与新状态）。  
  - [x] 2.2 确保由每日亏损限制等间接途径触发 Kill-Switch 时，同样能够走到统一的通知逻辑（避免多处复制）。  
  - [x] 2.3 为相关路径补充或更新结构化日志，保持与已有 Kill-Switch 日志、`ai_decisions.csv` 风控审计记录风格一致。

- [x] **Task 3 – 单元测试与回归验证（AC3, AC4）**  
  - [x] 3.1 为通知 helper 编写单元测试，使用 stub 的 `send_fn` 捕获文本内容与参数，验证激活/解除两类消息的字段与格式。  
  - [x] 3.2 为 Kill-Switch 生命周期添加或扩展测试（例如在 `tests/test_risk_control_integration.py` 或新的 `tests/test_notifications_telegram.py` 中），验证：  
        - 状态从 False→True / True→False 时会调用通知逻辑；  
        - 状态保持不变时不会重复触发通知。  
  - [x] 3.3 运行 `./scripts/run_tests.sh`，确保所有现有 Kill-Switch / 风控 / Telegram 相关测试继续通过，如有必要，仅在期望值层面调整新增日志或调用次数。

## Dev Notes

### Requirements & Context Summary

- 本 Story 属于 **Epic 7.2: Kill-Switch 核心功能**，对应 `sprint-status.yaml` 中的 key：`7-2-5-实现-kill-switch-状态变更通知`。  
- 需求主要来源：  
  - PRD 《风控系统增强 - 产品需求文档》（`docs/prd-risk-control-enhancement.md`）中的功能需求：  
    - **FR11**：Kill-Switch 状态变更时，系统发送 Telegram 通知；  
    - **FR19–FR20**：所有风控状态变更与事件需要在日志与 `ai_decisions.csv` 中留下可审计轨迹；  
    - 以及 Kill-Switch 成功/失败场景下的验收测试用例。  
  - Epic 文档 `docs/epic-risk-control-enhancement.md` 中 **Story 7.2.5: 实现 Kill-Switch 状态变更通知** 的描述：  
    - Kill-Switch 激活/解除时发送包含原因、时间、持仓数量与恢复指令提示的 Telegram 通知；  
    - 通知使用清晰的 Markdown 格式，并具备单元测试覆盖。  
  - 已完成的 Kill-Switch 相关 Stories：  
    - 7.2.1 / 7.2.2 / 7.2.3 / 7.2.4 已经实现 Kill-Switch 激活/解除逻辑、信号过滤与 SL/TP 行为保证；  
    - 当前 Story 在此基础上，聚焦于「状态变更时的用户可见通知与审计」。

### Learnings from Previous Story

**From Story 7-2-4-确保-sl-tp-在-kill-switch-期间正常工作 (Status: review / implementation completed)**

- **Kill-Switch 与 SL/TP 的边界已被明确验证：**  
  - Kill-Switch 仅阻止新的 `signal="entry"`，不会阻止 `signal="close"` 以及由 SL/TP 触发的平仓；  
  - 在 Kill-Switch 激活期间，纸上模式下的 SL/TP 行为与基线完全一致；Hyperliquid 实盘模式下保持原有「本地 SL/TP 不执行」的语义。  
- **现有测试覆盖了 Kill-Switch + SL/TP 的关键路径：**  
  - `tests/test_stop_loss_take_profit.py` 与 `tests/test_risk_control_integration.py` 中已经有针对 Kill-Switch 激活/未激活组合的集成测试；  
  - 这些测试可作为本 Story 验收时的「副观察点」，确保新增通知逻辑不会意外改变 SL/TP 行为。  
- **对本 Story 的启示：**  
  - 新增的 Telegram 通知逻辑必须是「旁路的可观测性增强」，而不是改变 Kill-Switch 或 SL/TP 行为本身；  
  - 任何与 Kill-Switch 状态读取或写入相关的改动，都应复用现有 `core/risk_control.py` 与状态管理入口，避免在通知层新增第二套状态源。

### Architecture & Implementation Constraints

- **模块边界约束：**  
  - 风控状态与 Kill-Switch 语义：`core/risk_control.py` / `core/state.py`；  
  - 主循环与决策处理：`bot.py` / `core/trading_loop.py`；  
  - 通知与 Telegram 发送：`notifications/telegram.py` 及未来的命令处理模块。  
- **设计要求：**  
  - 通知构建与发送应保持与现有 `send_telegram_message(...)` 一致的错误处理与降级策略；  
  - 避免在多处复制 Bot Token / Chat ID 解析逻辑，优先复用已有配置或集中封装；  
  - 通知逻辑应易于在测试中 stub/mock（例如通过依赖注入 send 函数）。

### Project Structure Notes

- 预计主要涉及文件（最终以实际实现为准）：  
  - `core/risk_control.py` —— 在 Kill-Switch 激活/解除函数或调用点挂接通知逻辑；  
  - `core/state.py` / `core/persistence.py` —— 如需从持仓或状态对象中提取当前持仓数量，作为通知上下文的一部分；  
  - `notifications/telegram.py` —— 复用或扩展现有 Telegram 发送工具，增加 Kill-Switch 专用通知 helper；  
  - `tests/test_risk_control_integration.py`、`tests/test_notifications_telegram.py`（或等价文件）—— 补充单元与集成测试。

### References

- [Source: docs/prd-risk-control-enhancement.md#Kill-Switch-功能]  
- [Source: docs/prd-risk-control-enhancement.md#日志与审计]  
- [Source: docs/epic-risk-control-enhancement.md#Story-7.2.5-实现-Kill-Switch-状态变更通知]  
- [Source: docs/sprint-artifacts/7-2-3-实现信号过滤逻辑.md]  
- [Source: docs/sprint-artifacts/7-2-4-确保-sl-tp-在-kill-switch-期间正常工作.md]  
- [Source: notifications/telegram.py]

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/7-2-5-实现-kill-switch-状态变更通知.context.xml

### Agent Model Used

- Cascade

### Debug Log References

- 分析了 `core/risk_control.py` 中的 Kill-Switch 生命周期，确定 `activate_kill_switch` 和 `deactivate_kill_switch` 是状态变更的唯一入口
- 决定在这两个函数中添加可选的 `notify_fn` 回调参数，保持向后兼容性
- 通知回调通过工厂函数 `create_kill_switch_notify_callbacks` 创建，封装 Telegram 配置

### Completion Notes List

- **实现方案：** 采用回调注入模式，在 `activate_kill_switch` 和 `deactivate_kill_switch` 函数中添加可选的 `notify_fn` 参数
- **消息格式：** 使用 MarkdownV2 格式，包含 emoji、触发原因、时间戳、持仓数量等信息
- **幂等性保证：** 仅在状态实际发生变化时（inactive→active 或 active→inactive）才触发通知
- **错误处理：** 通知失败不会影响主逻辑，异常被捕获并记录到日志
- **测试覆盖：** 新增 32 个单元测试，覆盖消息构建、发送、配置缺失、幂等性等场景
- **全量测试：** 508 个测试全部通过

### Completion Notes
**Completed:** 2025-11-30  
**Definition of Done:** All acceptance criteria met, code reviewed, tests passing

### File List

**新增文件：**
- `tests/test_kill_switch_notifications.py` - Kill-Switch 通知功能的单元测试

**修改文件：**
- `notifications/telegram.py` - 添加 Kill-Switch 通知 helper 函数
  - `build_kill_switch_activated_message()` - 构建激活通知消息
  - `build_kill_switch_deactivated_message()` - 构建解除通知消息
  - `notify_kill_switch_activated()` - 发送激活通知
  - `notify_kill_switch_deactivated()` - 发送解除通知
  - `create_kill_switch_notify_callbacks()` - 创建通知回调工厂函数
- `core/risk_control.py` - 修改 Kill-Switch 函数支持通知回调
  - `activate_kill_switch()` - 添加 `notify_fn` 和 `positions_count` 参数
  - `deactivate_kill_switch()` - 添加 `notify_fn` 参数
  - `apply_kill_switch_env_override()` - 添加通知回调参数
- `core/state.py` - 在 `load_state()` 中集成通知回调
- `tests/test_risk_control.py` - 更新日志格式断言以匹配新格式

### Change Log

- 2025-11-30: 实现 Kill-Switch 状态变更通知功能（Story 7.2.5）
