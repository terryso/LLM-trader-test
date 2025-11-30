# Story 7.2.2: 实现 Kill-Switch 解除逻辑

Status: done

## Story

As a trading-bot operator who has previously activated the Kill-Switch,
I want a safe and explicit way to deactivate the Kill-Switch and resume trading once the issue is resolved,
so that I can restore normal operation without manually editing state files or accidentally bypassing risk controls.

## Acceptance Criteria

1. **AC1 – Kill-Switch 解除语义与状态约束**  
   - 系统为 Kill-Switch 提供**单一真实来源**的解除逻辑（例如 `deactivate_kill_switch(...)`），集中在 `core/risk_control.py` 中实现。  
   - 当 Kill-Switch 处于激活状态（`kill_switch_active=True`）时调用解除逻辑：  
     - 将 `kill_switch_active` 置为 `False`；  
     - 为 `kill_switch_reason` 写入清晰的解除原因（例如 `"runtime:resume"` 或等价语义），用于审计追踪；  
     - 不清空 `kill_switch_triggered_at` 字段，保留最近一次激活时间供后续分析使用。  
   - 解除逻辑**不修改**每日亏损相关字段（`daily_start_equity` / `daily_start_date` / `daily_loss_pct` / `daily_loss_triggered`），为 Epic 7.3 预留职责边界。

2. **AC2 – 与风控检查入口和主循环的集成**  
   - 在 Kill-Switch 激活后调用解除逻辑：  
     - 后续对 `core/risk_control.check_risk_limits(...)` 的调用将返回「允许新开仓」的结果（在无其他风控约束的前提下）；  
     - 交易主循环 `_run_iteration()` / `process_ai_decisions()` 中对 `allow_entry` 的使用无需修改调用点，只依赖 `check_risk_limits(...)` 的返回值变化。  
   - 调用解除逻辑并通过 `core.state.save_state()` 持久化后：  
     - 在 **未显式设置 `KILL_SWITCH` 环境变量** 的前提下，下次 Bot 启动并执行 `load_state()` 后，Kill-Switch 处于未激活状态；  
     - 若 `KILL_SWITCH=true` 明确设置，则仍以环境变量为准，启动后 Kill-Switch 继续保持激活（不得被持久化状态的解除结果覆盖）。

3. **AC3 – 日志与审计事件**  
   - 当 Kill-Switch 被解除时，系统至少记录一条结构化日志（INFO 或 WARNING）：  
     - 包含字段：先前状态（active/inactive）、解除原因、是否由每日亏损触发过（`daily_loss_triggered`）、当前总权益或等价上下文。  
   - 如在 7-2-1 中已引入 `RISK_CONTROL` 类型的 `ai_decisions.csv` 记录，本 Story 在解除路径上补充对应记录或明确说明为何不需要，保证 Kill-Switch 生命周期的审计链条完整。

4. **AC4 – 持久化与重启场景测试**  
   - 新增或扩展集成测试，覆盖以下场景：  
     - 场景 A：通过编程方式激活 Kill-Switch → 运行若干迭代 → 调用解除逻辑 → 保存状态 → 重启后，在 `KILL_SWITCH` 未显式设置时，Kill-Switch 处于未激活状态且不再阻止 entry。  
     - 场景 B：在 `KILL_SWITCH=true` 环境变量下启动 Bot，尝试在运行期调用解除逻辑 → 即使本次运行内可以临时放行或不放行，**重启后仍以环境变量为准**，Kill-Switch 重回激活状态。  
     - 场景 C：状态文件损坏或缺失时的回退行为仍由 Epic 7.1 实现的逻辑负责，本 Story 不引入新的未捕获异常路径。

5. **AC5 – 与后续 Epic 的边界与契约清晰**  
   - 明确记录本 Story 对 PRD 中 Kill-Switch 功能（FR5–FR11）和「恢复机制可靠性」的覆盖范围：  
     - 仅负责 Kill-Switch 解除的**内部语义与状态管理**；  
     - Telegram `/resume` 命令与通知由 Epic 7.4 的 Stories 实现；  
     - 每日亏损触发 Kill-Switch 的逻辑及其重置/确认流程由 Epic 7.3 负责。  
   - 在 Dev Notes 中描述，后续 Telegram 命令或 UX 层调用 Kill-Switch 解除逻辑时，应优先通过 `core/risk_control` 提供的统一接口，而非直接篡改 JSON 文件。

## Tasks / Subtasks

- [x] **Task 1 – 明确 Kill-Switch 解除语义与 API（AC1, AC5）**  
  - [x] 1.1 通读 `core/risk_control.py` 现有的 `activate_kill_switch()` / `deactivate_kill_switch()` / `apply_kill_switch_env_override()` 实现，整理当前状态字段和日志模式。  
  - [x] 1.2 在 Dev Notes 中给出 Kill-Switch 生命周期状态机（激活 → 持久化 → 解除 → 重启）的文字描述，确保与 PRD/Tech Spec 一致。  
  - [x] 1.3 如有需要，对 `deactivate_kill_switch()` 的签名和内部实现做最小调整，使其成为唯一权威的解除入口。

- [x] **Task 2 – 集成到风控检查与主循环（AC2）**  
  - [x] 2.1 确认 `check_risk_limits(...)` 目前对 Kill-Switch 的判断路径，并在解除后返回「允许 entry」的结果。  
  - [x] 2.2 在 `_run_iteration()` / `process_ai_decisions()` 的调用链上验证：Kill-Switch 解除后，LLM 的 `signal="entry"` 决策可以再次通过风控检查进入执行层。  
  - [x] 2.3 确认不需要在执行层二次修改 Kill-Switch 相关逻辑，如有 defense-in-depth 守卫，确保其行为与解除语义一致。

- [x] **Task 3 – 持久化与重启行为验证（AC2, AC4）**  
  - [x] 3.1 为解除场景新增集成测试（可复用 7-2-1 的测试夹具），覆盖持久化与重启后的 Kill-Switch 状态。  
  - [x] 3.2 在环境变量与持久化状态冲突的场景下（`KILL_SWITCH=true` 且状态文件记录未激活），验证始终以环境变量为准。

- [x] **Task 4 – 日志与审计完善（AC3, AC5）**  
  - [x] 4.1 在 Kill-Switch 解除路径中添加结构化日志条目，并与 7-2-1 中的激活日志保持风格一致。  
  - [x] 4.2 视需要扩展 `tests/test_risk_control_integration.py` 或相关测试，验证关键日志是否产生。  
  - [x] 4.3 对照 PRD FR19–FR20 和 7.1 Retro 的建议，确认 Kill-Switch 激活与解除在日志和审计层面形成完整闭环。

## Dev Notes

### Requirements & Context Summary

- 本 Story 属于 **Epic 7.2: Kill-Switch 核心功能**，对应 `sprint-status.yaml` 中的 key：`7-2-2-实现-kill-switch-解除逻辑`，标记为 Post-MVP 能力。  
- 需求来源：  
  - PRD《风控系统增强 - 产品需求文档》（`docs/prd-risk-control-enhancement.md`）中关于 Kill-Switch 的功能与「恢复机制可靠性」：  
    - Kill-Switch 激活后需要有明确的恢复路径（FR5–FR11）。  
    - 恢复操作需要确认，并且所有状态变更要有完整日志记录。  
  - Epic 7.2 概述与故事列表：在 7-2-1 实现激活逻辑后，本 Story 聚焦于 Kill-Switch 的**解除语义与状态管理**，为后续 Telegram 命令与每日亏损逻辑提供稳定基座。  
  - Tech Spec `tech-spec-epic-7-1.md` 与 `epic-7-1-retro-risk-control.md` 中关于：  
    - 环境变量与持久化状态优先级（环境变量优先）；  
    - `RiskControlState` 字段含义与向后兼容策略；  
    - 在 `check_risk_limits()` 中预留 Kill-Switch / 每日亏损检查入口。

### Learnings from Previous Story

**From Story 7-2-1-实现-kill-switch-激活逻辑 (Status: done)**

- **现有能力**  
  - 已实现 `activate_kill_switch()` / `deactivate_kill_switch()` / `apply_kill_switch_env_override()` 等帮助函数，Kill-Switch 状态集中在 `core/risk_control.py` 管理。  
  - `check_risk_limits(...)` 在每轮 `_run_iteration()` 开始阶段调用，当 `kill_switch_active=True` 且 `RISK_CONTROL_ENABLED=True` 时，会返回「禁止新开仓」的信号，并在主循环和执行层实现 defense-in-depth。  
  - `core/state.load_state()` 在加载状态后应用 `KILL_SWITCH` 环境变量覆盖逻辑：显式设置的 `KILL_SWITCH=true/false` 优先于 `portfolio_state.json.risk_control.kill_switch_active`。

- **架构与实现模式**  
  - **单一状态入口**：所有风控状态读写均通过 `core.state` / `core.persistence` 与 `RiskControlState`，不允许在其他模块单独维护布尔副本。  
  - **原子持久化**：风控状态与投资组合状态在同一个 JSON 内通过原子写入保存，保证在崩溃或中断时不会生成损坏文件。  
  - **双层防护**：主循环在决策入口处根据 `allow_entry` 决定是否处理 entry，执行层在 `execute_entry` 中仍保留 Kill-Switch 终极守卫。

- **对本 Story 的启示**  
  - 解除逻辑应尽量复用并扩展现有 `deactivate_kill_switch()`，避免在多个模块中出现平行实现。  
  - 任何新的「恢复」行为都必须遵守「环境变量优先」与「配置 / 状态 / 行为三层分离」原则：  
    - 本 Story 聚焦状态与行为，不在配置层引入新的环境变量。  
  - 集成测试应沿用 7-2-1 中的模式：通过 end-to-end 风控检查 + 状态持久化 + 重启组合验证行为，而不仅是单纯单元测试。

### Architecture & Implementation Constraints

- **模块边界**  
  - Kill-Switch 状态与解除语义：`core/risk_control.py` / `core/state.py`。  
  - 主循环入口与决策处理：`bot.py` / `core/trading_loop.py`。  
  - 执行路径与最终守卫：`execution/executor.py`。  
  - 日志与未来通知：`notifications/logging.py`，Telegram 通知由 Epic 7.4 负责。  
- **禁止事项**  
  - 禁止直接在 `bot.py`、`execution/` 或 `notifications/telegram.py` 中修改 `RiskControlState` 内部字段，应通过封装好的 API 进行。  
  - 禁止在本 Story 中调整每日亏损相关字段的含义或默认值，以避免与 Epic 7.3 的职责重叠。  

### Project Structure Notes

- 预计主要改动文件：  
  - `core/risk_control.py` —— 明确并实现 Kill-Switch 解除 API 与日志。  
  - `core/state.py` —— 如有需要，确保 `load_state()` / `save_state()` 对解除后的状态持久化行为正确。  
  - `bot.py` / `core/trading_loop.py` —— 通过集成测试验证解除后 `allow_entry` 行为，无需大规模重构。  
  - `tests/test_risk_control.py`、`tests/test_risk_control_integration.py` —— 为解除与重启场景新增测试用例。  

### References

- [Source: docs/prd-risk-control-enhancement.md#Kill-Switch（紧急停止）]  
- [Source: docs/prd-risk-control-enhancement.md#成功标准]  
- [Source: docs/sprint-artifacts/tech-spec-epic-7-1.md#Acceptance-Criteria-Authoritative]  
- [Source: docs/sprint-artifacts/epic-7-1-retro-risk-control.md]  
- [Source: docs/sprint-artifacts/7-2-1-实现-kill-switch-激活逻辑.md]  
- [Source: docs/architecture/03-data-flow.md]  
- [Source: docs/architecture/06-project-structure-and-mapping.md]  
- [Source: docs/architecture/07-implementation-patterns.md]

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/7-2-2-实现-kill-switch-解除逻辑.context.xml

### Agent Model Used

- Cascade

### Debug Log References

- Kill-Switch 解除日志：  
  - `Kill-Switch deactivated: previous_state=active, previous_reason=%s, deactivation_reason=%s, daily_loss_triggered=%s, total_equity=%.2f`（INFO 级别）  
  - `Kill-Switch deactivate called but was already inactive: reason=%s`（DEBUG 级别）

### Completion Notes List

- ✅ **AC1 实现**：修改 `deactivate_kill_switch()` 函数签名，添加 `reason` 和 `total_equity` 参数：
  - `reason` 参数用于记录解除原因（默认 `"runtime:resume"`），支持审计追踪
  - 保留 `kill_switch_triggered_at` 字段，不再清空，供后续分析使用
  - 不修改每日亏损相关字段（`daily_start_equity` / `daily_start_date` / `daily_loss_pct` / `daily_loss_triggered`）
- ✅ **AC2 验证**：确认 `check_risk_limits()` 在 Kill-Switch 解除后返回 `True`（允许 entry），主循环和执行层无需修改
- ✅ **AC3 实现**：在 `deactivate_kill_switch()` 中添加结构化 INFO 日志，包含先前状态、解除原因、`daily_loss_triggered` 和总权益
- ✅ **AC4 测试**：新增 `KillSwitchDeactivationIntegrationTests` 测试类，覆盖场景 A（解除后重启）和场景 B（环境变量优先级）
- ✅ **AC5 边界**：本 Story 仅负责 Kill-Switch 解除的内部语义与状态管理；Telegram `/resume` 命令由 Epic 7.4 实现；每日亏损重置由 Epic 7.3 实现
- ✅ **关于 ai_decisions.csv**：Story 7-2-1 中 `RISK_CONTROL` 类型记录为可选实现，本 Story 通过结构化日志满足审计需求，不额外添加 CSV 记录
- ✅ 测试套件从 459 增加到 466 个测试（新增 7 个测试），全部通过

### Kill-Switch 生命周期状态机

```
[未激活] --activate_kill_switch(reason)--> [激活]
    ^                                          |
    |                                          v
    +---deactivate_kill_switch(reason)----[解除]
                                               |
                                               v
                                    [持久化 save_state()]
                                               |
                                               v
                                    [重启 load_state()]
                                               |
                                               v
                        [apply_kill_switch_env_override()]
                                               |
                                               v
                        [env 优先级决定最终状态]
```

**关键规则：**
- 环境变量 `KILL_SWITCH=true/false` 始终优先于持久化状态
- 解除后保留 `kill_switch_triggered_at` 供审计
- 解除时写入新的 `kill_switch_reason`（如 `"runtime:resume"`）
- 后续 UX 或 Telegram 命令层应通过 `core.risk_control.deactivate_kill_switch()` 调用解除逻辑，而非直接篡改 JSON 状态文件

### File List

- **MODIFIED** `core/risk_control.py` — 更新 `deactivate_kill_switch()` 签名和实现，添加 `reason`/`total_equity` 参数，保留 `kill_switch_triggered_at`，添加结构化日志
- **MODIFIED** `tests/test_risk_control.py` — 更新 `TestDeactivateKillSwitch` 测试类，新增 5 个测试用例覆盖新 API 和日志
- **MODIFIED** `tests/test_risk_control_integration.py` — 新增 `KillSwitchDeactivationIntegrationTests` 测试类（4 个测试），覆盖 AC4 场景 A/B 和 AC1 审计追踪

## Change Log

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 0.1 | 2025-11-30 | Nick (SM) | 初始 Story 草稿（通过 create-story 工作流生成，定义 Kill-Switch 解除逻辑的需求与范围） |
| 1.0 | 2025-11-30 | Cascade | 完成所有 Tasks 和 AC，实现 Kill-Switch 解除逻辑，新增 7 个测试用例 |
| 1.1 | 2025-11-30 | Cascade | Senior Developer Review (AI) 完成，状态更新为 done |

## Senior Developer Review (AI)

### Reviewer

Cascade (AI)

### Date

2025-11-30

### Outcome

**Approve** ✅

所有 Acceptance Criteria 均已实现，所有标记为完成的 Tasks/Subtasks 均已在代码和测试中得到验证。本次实现严格遵守 Epic 7.2 / 7.1 的数据模型与环境变量优先级约定，未发现需要阻塞上线的架构或质量问题。

### Summary

- `deactivate_kill_switch()` 被提升为 Kill-Switch 解除的单一权威入口，明确了解除语义：
  - `kill_switch_active` 置为 `False`
  - `kill_switch_reason` 更新为解除原因（默认 `"runtime:resume"`，也支持 `"telegram:/resume"`、`"env:KILL_SWITCH"` 等）
  - `kill_switch_triggered_at` 保留，满足审计与分析需要
  - 每日亏损字段保持不变，为 Epic 7.3 预留职责
- 风控检查入口 `check_risk_limits()` 与主循环/执行层的 Kill-Switch 流程保持一致：
  - 激活 → `check_risk_limits()` 返回 `False`、主循环禁止 entry、执行层守卫兜底
  - 解除 → `check_risk_limits()` 返回 `True`，entry 可以正常恢复
- 新增集成测试精确覆盖持久化与重启行为，验证在有/无 `KILL_SWITCH` 环境变量时的差异化语义
- 解除路径增加结构化 INFO 日志，补足 Kill-Switch 生命周期的审计链条

### Acceptance Criteria Coverage

| AC | Description | Status | Evidence |
|---|---|---|---|
| AC1 | Kill-Switch 解除语义与状态约束 | ✅ IMPLEMENTED | `core/risk_control.py:161-208`; `tests/test_risk_control.py:307-387`; `tests/test_risk_control_integration.py:999-1043` |
| AC2 | 与风控检查入口和主循环的集成 | ✅ IMPLEMENTED | `core/risk_control.py:75-125`; `bot.py:608-615`; `tests/test_risk_control_integration.py:577-606, 864-939` |
| AC3 | 日志与审计事件 | ✅ IMPLEMENTED | `core/risk_control.py:191-201`; `tests/test_risk_control.py:342-359` |
| AC4 | 持久化与重启场景测试 | ✅ IMPLEMENTED | `tests/test_risk_control_integration.py:864-939, 999-1043, 1045-1090` |
| AC5 | 与后续 Epic 的边界与契约清晰 | ✅ IMPLEMENTED | `docs/sprint-artifacts/7-2-2-实现-kill-switch-解除逻辑.md:103-121`; 未发现跨 Epic 职责越界变更 |

**Summary**: 5 of 5 acceptance criteria fully implemented.

### Task Completion Validation

| Task | Marked As | Verified As | Evidence |
|---|---|---|---|
| 1.1 通读 core/risk_control.py 并整理状态字段与日志模式 | ✅ Completed | ✅ VERIFIED COMPLETE | Dev Notes 中的状态机与字段说明；后续实现与测试均基于统一语义 |
| 1.2 在 Dev Notes 中给出 Kill-Switch 生命周期状态机 | ✅ Completed | ✅ VERIFIED COMPLETE | `7-2-2-实现-kill-switch-解除逻辑.md:162-181` |
| 1.3 调整 deactivate_kill_switch() 使其成为唯一解除入口 | ✅ Completed | ✅ VERIFIED COMPLETE | `core/risk_control.py:161-208`; 仅测试和 env override 调用该函数 |
| 2.1 确认 check_risk_limits(...) 在解除后返回允许 entry | ✅ Completed | ✅ VERIFIED COMPLETE | `core/risk_control.py:75-125`; `tests/test_risk_control.py:495-557` |
| 2.2 验证 `_run_iteration()` / `process_ai_decisions()` 在解除后放行 entry | ✅ Completed | ✅ VERIFIED COMPLETE | `bot.py:608-615`; Kill-Switch 逻辑沿用 7-2-1 已有测试，解除后 allow_entry=True 不再阻塞 |
| 2.3 确认执行层守卫行为与解除语义一致 | ✅ Completed | ✅ VERIFIED COMPLETE | `execution/executor.py` 守卫逻辑保持不变；Kill-Switch 解除后回调返回 False，集成测试 `ExecutorKillSwitchGuardTests` 仍通过 |
| 3.1 为解除场景新增集成测试（持久化+重启） | ✅ Completed | ✅ VERIFIED COMPLETE | `tests/test_risk_control_integration.py:864-939` |
| 3.2 在 `KILL_SWITCH=true` 场景下验证 env 优先级 | ✅ Completed | ✅ VERIFIED COMPLETE | `tests/test_risk_control_integration.py:941-997` |
| 4.1 在解除路径中添加结构化日志条目 | ✅ Completed | ✅ VERIFIED COMPLETE | `core/risk_control.py:191-201`; `tests/test_risk_control.py:342-359` |
| 4.2 扩展集成测试验证关键日志/状态 | ✅ Completed | ✅ VERIFIED COMPLETE | `tests/test_risk_control_integration.py:999-1043, 1045-1090` |
| 4.3 对照 PRD/Retro 形成完整激活-解除审计闭环 | ✅ Completed | ✅ VERIFIED COMPLETE | Story Dev Notes 与实现保持一致；激活路径沿用 7-2-1，解除路径新增日志与测试 |

**Summary**: 11 of 11 completed tasks verified, 0 questionable, 0 false completions.

### Test Coverage and Gaps

- 总计 466 个测试全部通过，其中本 Story 直接新增/强化：
  - 单元测试：`TestDeactivateKillSwitch`（5 个用例）、`TestApplyKillSwitchEnvOverride` 中 env=false 行为调整
  - 集成测试：`KillSwitchDeactivationIntegrationTests`（4 个场景）
- AC 映射：
  - AC1/AC3 → `tests/test_risk_control.py::TestDeactivateKillSwitch`
  - AC2 → `tests/test_risk_control.py::TestCheckRiskLimitsKillSwitch` + 7-2-1 已有集成测试
  - AC4 → `tests/test_risk_control_integration.py::KillSwitchDeactivationIntegrationTests`
- 未发现明显测试缺口；每日亏损相关逻辑仍按 Epic 7.3 计划在后续 Story 中实现。

### Architectural Alignment

- Kill-Switch 状态与解除逻辑严格限定在 `core/risk_control.py` / `core/state.py` 层；上层通过 `check_risk_limits()` 与 `risk_control_state` 使用结果，不直接篡改 JSON。
- 未引入新的环境变量；继续遵守「环境变量优先于持久化状态」的既有契约。
- 执行层 (`execution/executor.py`) 继续作为最终守卫，通过回调 `is_kill_switch_active` 获取状态，未破坏分层。

### Security Notes

- 本 Story 不引入外部输入或新配置项，主要改动集中在内部状态管理与日志。
- 解除逻辑不会绕过未来每日亏损限制的 env 规则（AC5 已限定），不存在显著安全风险。

### Best-Practices and References

- 继续使用 `dataclasses.replace()` 维护不可变状态更新模式，有利于测试与推理。
- Kill-Switch 生命周期（激活→持久化→解除→重启）通过集成测试完整覆盖，符合可靠性要求。
- 日志信息结构化且可 grep，便于后续监控与审计。

### Action Items

**Code Changes Required:**

- 无需额外代码修改；当前实现可以进入下一步验收/上线流程。

**Advisory Notes:**

- Note: 如未来在 `ai_decisions.csv` 中引入 `action="RISK_CONTROL"` 记录，可在解除路径复用同一 schema，形成更完整的 CSV 审计链条（当前通过结构化日志已满足 AC3 要求）。
- Note: 若后续 Epic 7.3/7.4 引入更复杂的恢复策略（例如按每日亏损状态决定是否允许恢复），建议在 Tech Spec 中扩展 `deactivate_kill_switch()` 的参数和语义，而非在调用方散落条件判断。
