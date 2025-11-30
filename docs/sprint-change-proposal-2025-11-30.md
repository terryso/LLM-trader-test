# Sprint Change Proposal – 风控系统增强（Epic 7.x）对齐与范围调整

Date: 2025-11-30  
Author: Nick (with Cascade, via correct-course)

---

## 1. Issue Summary

### 1.1 触发背景

- 在原始 `docs/epics.md` 中，仅规划并记录了：
  - **Epic 1**：支持任意 OpenAI 协议兼容 LLM 提供商；
  - **Epic 6**：统一交易所执行层 & 多交易所可插拔支持。
- 随着项目推进，已经为「风控系统增强」新增了一整套工件：
  - **PRD**：`docs/prd-risk-control-enhancement.md` 定义 Kill-Switch、每日亏损限制、Telegram 命令等能力；
  - **Tech Spec**：`docs/sprint-artifacts/tech-spec-epic-7-1.md` 描述风控状态基础设施；
  - **Epic Retro**：`docs/sprint-artifacts/epic-7-1-retro-risk-control.md` 记录 Epic 7.1 实施经验；
  - **Sprint Tracking**：`docs/sprint-artifacts/sprint-status.yaml` 中已经跟踪 Epic 7.1–7.4 及其 Stories；
  - **新 Story**：7-2-1-实现-kill-switch-激活逻辑 已完成 Story 草稿与 context，并标记为 `ready-for-dev`。
- 但这些工作尚未反映在 `docs/epics.md` 的 Epic 列表和 Summary 中，主 PRD (`docs/prd.md`) 也只在路线图中略提应急控制，无正式 Epic/Story 级对齐。

### 1.2 核心问题（Problem Statement）

> 风控增强（Epic 7.x）在 PRD / Tech Spec / Sprint 状态中已经被实质性规划和部分实现，但上游 Epic 文档和整体路线图尚未与之对齐，导致：
>
> - MVP 与 Post-MVP 范围在风控维度不清晰；
> - `epics.md` 未暴露 Epic 7.x，对外呈现的项目「大图」与实际开发偏离；
> - 未来 Story 规划与优先级讨论缺少统一锚点。

---

## 2. Impact Analysis

### 2.1 Epic 层影响

- **新能力线的引入**：
  - 需要在 Epic 级别正式引入 **Epic 7: 风控系统增强（Emergency Controls）**，并拆分为：
    - Epic 7.1：风控状态管理基础设施；
    - Epic 7.2：Kill-Switch 核心功能；
    - Epic 7.3：每日亏损限制功能；
    - Epic 7.4：Telegram 命令集成。
- **现状与规划状态**：
  - Epic 7.1 已完整实现（7-1-1~7-1-4 全部 done，有 Tech Spec & Retro & Tests）；
  - Story 7-2-1 已起草并 context 化、标记为 `ready-for-dev`；
  - 其余 7.2.x / 7.3.x / 7.4.x 在 PRD 和 sprint-status 中已被列出，但尚未进入实现阶段（backlog）。

### 2.2 PRD 与 FR 影响

- `docs/prd.md`：
  - 在主 PRD 中，风控增强目前主要作为路线图方向出现（例如「更完备的 Hyperliquid 实盘功能与应急控制（Kill-Switch、滑点跟踪等）」），尚未以独立 Epic 或 FR 组的形式呈现；
  - 需要在合适位置明确挂接：
    - 「风控系统增强 – 参见 `docs/prd-risk-control-enhancement.md`」；
    - 指出其中哪些能力属于当前 MVP，哪些为 Post-MVP。
- `docs/prd-risk-control-enhancement.md`：
  - 已经定义了详细的 FR1–FR24 / NFR1–NFR10，但是：
    - 没有在 `docs/epics.md` 的 FR Coverage Matrix 中露出；
    - 与 Epic/Story ID（7-1-x / 7-2-x / 7-3-x / 7-4-x）的映射主要通过文字描述完成，缺乏表格级总结。

### 2.3 架构与实现文档影响

- `docs/architecture/*.md` 与 Tech Spec 已经：
  - 将 `core/risk_control.py`、`core/state.py`、`bot.py` 等组件纳入架构视图；
  - 描述了主循环中风控检查的插入点与状态持久化路径；
  - 明确了 Kill-Switch 与每日亏损相关字段的 schema 与日志策略。
- 架构层目前**不与 Epic 7.x 冲突**，只是缺少：
  - 「哪个 Epic/Story 负责兑现哪一部分架构约束」的聚合视图；
  - 风控增强对整体系统目标（安全性、可观测性）的贡献在高层 summary 中未被点名。

### 2.4 Sprint / Backlog 影响

- `sprint-status.yaml`：
  - 已将 Epic 7.1 标记为 `contexted`，其下所有 Story 标记为 `done`；
  - 已为 Epic 7.2–7.4 建立 Story 行，其中 7-2-1 的状态为 `ready-for-dev`；
  - 与 `docs/epics.md` 当前只包含 Epic 1 / 6 的状态明显不一致。
- 风险：
  - 若不更新 `docs/epics.md` 与相关 PRD Summary，团队在阅读文档时会低估风控路线的复杂度与优先级，影响后续规划与沟通。

---

## 3. Recommended Approach

### 3.1 评估的选项

- **Option 1 – 直接调整（推荐）**  
  在现有实现之上，对 `epics.md`、风控 PRD 和 sprint 追踪做小范围、一致性修正：
  - 在 `docs/epics.md` 中正式引入 Epic 7.x；
  - 在风控 PRD 中标注 MVP 与 Post-MVP 范围，并与 Epic/Story ID 对齐；
  - 保持已完成的 Epic 7.1 与正在推进的 7-2-1 不变。

- **Option 2 – 回滚最近 Story**  
  不适用：
  - Epic 7.1 已完整交付且测试充分（420+ Test 全绿），无回滚价值；
  - 当前问题是「路线图与文档偏离」，不是实现质量问题。

- **Option 3 – PRD MVP 大改**  
  在主 PRD 层面对整体 MVP 重新定义。当前评估结果：
  - **不需要大改主 PRD**，只需在主 PRD 中清晰挂接「风控增强」（指向独立风控 PRD），并在风控 PRD 内标明 MVP/后续能力区分即可。

### 3.2 推荐路径（Hybrid：Option 1 + 轻量 Option 3）

- 采用 **Option 1 为主、Option 3 轻量补充** 的策略：
  1. 在 `docs/epics.md` 中补充 Epic 7 区块，并更新 Summary 为「3 个 Epic」。
  2. 在风控 PRD 中显式声明：MVP 至少包含 Epic 7.1 全部 + Story 7-2-1，其余 Story 默认 Post-MVP。
  3. 保持主 PRD `docs/prd.md` 不大幅修改，仅在适当位置引用风控 PRD 作为应急控制子路线。

- **范围分类**：
  - 变更范围：**Minor~Moderate**（主要为文档与 Backlog 对齐，无需大规模代码重构）。
  - 对时间线影响：低（不改变当前 7.2.1 实现节奏）。
  - 技术风险：低（更清晰的文档有助于降低后续风险）。

---

## 4. Detailed Change Proposals

### 4.1 `docs/epics.md` 变更

**已执行的修改（Incremental 模式）**：

1. **Summary 更新**  
   - 原文：
     - 「当前版本包含 2 个已规划 Epic：」
     - 仅列出 Epic 1 与 Epic 6。
   - 新文：
     - 「当前版本包含 3 个已规划 Epic：」
     - 列出：
       - 平台能力 Epic 1（LLM 提供商统一访问）；
       - 交易执行 Epic 6（统一交易所执行层）；
       - 安全与风控 Epic 7（风控系统增强 / Emergency Controls）。

2. **新增 Epic 7 区块**  
   - 标题：`## Epic 7: 风控系统增强（Emergency Controls）`
   - 内容结构：
     - Epic 7 概述：背景、目标；
     - Epic 7.1（MVP）：范围 + Story 列表 + Tech Spec / PRD / Retro 引用；
     - Epic 7.2（部分纳入 MVP）：范围 + MVP 子集 Story 7-2-1 + 后续 7-2-2~7-2-5 标记为 Post-MVP；
     - Epic 7.3（Post-MVP）：每日亏损限制功能 + 7-3-1~7-3-4；
     - Epic 7.4（Post-MVP）：Telegram 命令集成 + 7-4-1~7-4-5。

> 状态：**已写入文件**，与当前 `sprint-status.yaml` 和风控 PRD 对齐。

### 4.2 `docs/prd.md` 建议（尚未执行，仅建议）

**建议性修改点：**

- 在「开放问题与后续路线」或合适章节中：
  - 将原本泛化的「Kill-Switch、滑点跟踪等」用语，替换为指向风控 PRD 的显式引用，例如：
    - 「有关 Kill-Switch / 每日亏损限制 / Telegram 风控命令的详细需求，参见 `docs/prd-risk-control-enhancement.md`。」
- 不在主 PRD 中重复风控细节，保持其为**总览文档**，具体需求由风控 PRD 承担。

> 状态：**尚未自动修改**，保留给你手工或后续迭代执行。

### 4.3 `docs/prd-risk-control-enhancement.md` 建议（尚未执行，仅建议）

- 在文档中新增一个小节，例如「MVP vs Post-MVP 范围」：
  - **MVP**：
    - 风控状态管理（FR1–FR4） → 对应 Epic 7.1 全部；
    - Kill-Switch 基础行为（FR5–FR8 中的「阻止 entry / 保留 close & SL/TP」）→ 对应 Story 7-2-1；
  - **Post-MVP**：
    - Kill-Switch 恢复与通知（FR9–FR11）；
    - 每日亏损限制（FR12–FR18）；
    - Telegram 命令集成（FR19–FR24）。
- 可选：增加一张简短表格，映射 FR 组到 Epic/Story ID，便于追踪。

> 状态：**尚未自动修改**，待 PO/PM 视情况通过。

---

## 5. Implementation Handoff

### 5.1 变更范围与执行角色

- **Scope 分类**：
  - 当前已执行的 `epics.md` 调整：**Minor**（文档与 Backlog 对齐）。
  - 建议中的 PRD/风控-PRD 修订：**Moderate**（需要 PO/PM 参与确认文本与 MVP 范围）。

- **推荐执行路径**：
  - 开发 / SM 侧：
    - 已可直接基于 Epic 7.1 + Story 7-2-1 的 Story & Context 启动实现，无需等待 PRD 进一步润色；
    - 后续实现 7-2-2~7-2-5 / 7-3-x / 7-4-x 时，以本提案为路线参考。
  - PO / PM 侧（你可以兼任）：
    - 视需要采纳 4.2 / 4.3 中的 PRD 文本修改建议；
    - 决定哪些风险能力要纳入 MVP 的「硬验收」范围。

### 5.2 成功标准

- `docs/epics.md` 能准确反映当前已存在的 3 条能力线（Epic 1 / 6 / 7），且 Epic 7.x 的分解与 PRD / sprint-status 一致；
- 对于风控增强：
  - 所有参与者都能从 `epics.md` 与 `prd-risk-control-enhancement.md` 中清楚理解：
    - MVP 要求是什么（7.1 + 7-2-1）；
    - 哪些能力会在后续迭代交付（7.2.2+ / 7.3.x / 7.4.x）。
- Story 7-2-1 的实现与测试按计划推进，不再受「上游文档不清晰」的阻碍。

---

> 若你认可本提案，可以：
> - 直接继续使用 `/dev-story` 针对 7-2-1 开始实现；
> - 或让我在后续迭代中，按上述建议继续帮你微调 PRD / 风控 PRD 的文本与 FR 映射。
