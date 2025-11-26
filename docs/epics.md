# LLM-trader-test - Epic Breakdown

**Author:** Nick  
**Date:** 2025-11-26  
**Project Level:** trading-bot  
**Target Scale:** single-team

---

## Overview

本文件基于现有 `docs/prd.md` 的 MVP 功能，新增对后续工作重点的 Epic 分解，当前仅包含一个平台能力 Epic：

- 支持通过统一的 OpenAI 协议客户端访问任意兼容的 LLM 提供商（包括 OpenRouter、官方 OpenAI、自建 OpenAI-compatible 网关等）。

> 说明：本文件是活文档，后续可以继续追加更多 Epic 与对应 User Stories。

---

## Functional Requirements Inventory

- **FR-L1：统一的 OpenAI 协议 LLM 访问能力**  
  系统应通过一层通用的 OpenAI Chat Completions 客户端访问 LLM，只要对方提供兼容的 HTTP 接口即可；具体供应商（OpenRouter、OpenAI、自建网关等）通过配置而非代码决定。

---

## FR Coverage Map

- FR-L1 由 **Epic 1：支持任意 OpenAI 协议兼容 LLM 提供商** 覆盖，后续可以根据需要增加更多 Story 细化实现路径。

---

## Epic 1: 支持任意 OpenAI 协议兼容 LLM 提供商

### Epic 1 概述

**背景 / 问题**

- 当前系统仅通过 `OPENROUTER_API_KEY` 访问 LLM，实际依赖 OpenRouter 作为唯一入口。
- 市面上越来越多 LLM 服务提供「OpenAI 协议兼容」的 API（官方 OpenAI、DeepSeek 自建网关、本地 vLLM / OpenAI-compatible proxy 等）。
- 单一依赖 OpenRouter 带来成本、稳定性、合规和可迁移性方面的限制。

**目标**

- 为 Bot、回测以及相关脚本提供一层**统一的 OpenAI 协议 LLM 客户端**：
  - 只要服务支持 OpenAI Chat Completions 风格接口（如 `/v1/chat/completions`），就可以通过配置直接接入。
- 通过环境变量完成不同 LLM 提供商的切换，无需修改代码。
- 在不破坏现有 OpenRouter 工作方式的前提下，保留 OpenRouter 作为一种默认/可选后端。

**范围（In Scope）**

- 抽象出通用 LLM 客户端：支持 `base_url`、`api_key`、`model`、超时与重试策略配置。
- 使用环境变量控制 LLM 访问配置，例如（具体命名可在实现时细化）：
  - `LLM_API_BASE_URL`：OpenAI 协议兼容服务 base URL。
  - `LLM_API_KEY`：通用 API Key（与 `OPENROUTER_API_KEY` 兼容或提供迁移路径）。
  - `LLM_API_TYPE`：可选标识（如 `openrouter` / `openai` / `custom`），用于处理少量差异化 header。
- Bot 主循环、回测等统一改用该客户端，而不是直接依赖 OpenRouter 特定调用方式。
- 文档更新：
  - 在 PRD 的 LLM 配置章节中，明确说明支持任意 OpenAI 协议兼容 LLM 提供商（规划中）。
  - 在 README / 配置说明中给出如何切换到自建 OpenAI-compatible 网关的示例。

**非范围（Out of Scope）**

- 不为每个第三方提供商单独设计 UI 级或脚本级「专属配置向导」。
- 不保证兼容所有**非标准** OpenAI 协议变种（参数和路径完全自定义的接口）。
- 不在本 Epic 内实现「多提供商智能路由 / 负载均衡 / 流量分配」等高级能力（可作为后续独立 Epic）。

**验收标准（Done Criteria）**

1. 在下列三种场景中，仅通过环境变量即可完成切换，无需修改代码：
   - a. 使用 OpenRouter 作为 LLM 入口（保持当前默认行为）。
   - b. 使用官方 OpenAI 或其他公开 OpenAI-compatible 服务。
   - c. 使用本地或自建 OpenAI-compatible 网关（例如 `http://localhost:8000/v1`）。
2. 在上述三种场景中：
   - Bot 主循环能稳定完成多轮调用，`ai_decisions.csv` 与 `ai_messages.csv` 中有成功记录。
   - `backtest.py` 能在三种后端间切换运行并正常产出结果文件。
3. 当配置错误（base URL 不可达 / Key 无效等）时：
   - 有清晰错误日志，明确指出是「LLM 后端配置/连接问题」。
   - Bot 不会异常退出主循环，而是按既有错误策略记录并重试或优雅降级。
4. 文档层面：
   - 有简要文档说明如何通过 `.env` 配置不同类型 LLM 提供商。

---

### Story 1.1: 通过环境变量配置 OpenAI 协议 LLM 提供商

As a power user or DevOps engineer,  
I want to configure the OpenAI-compatible LLM provider via environment variables (base_url, api_key, model, type),  
So that I can switch between OpenRouter, OpenAI, and self-hosted gateways without changing code.

**Acceptance Criteria:**

- Given 已正确设置如下环境变量：
  - `LLM_API_BASE_URL`
  - `LLM_API_KEY`
  - `TRADEBOT_LLM_MODEL`（或等价配置）
- When 运行 `bot.py` 主循环若干轮次
- Then 所有 LLM 请求均发送到 `LLM_API_BASE_URL`，并且：
  - 返回结果被正常解析为 JSON，并写入 `ai_decisions.csv` / `ai_messages.csv`；
  - 不需要修改任何调用 LLM 的业务代码。

**And**：

- 更新一份示例 `.env` 片段，展示三种典型配置：OpenRouter / OpenAI / 自建网关。

**Prerequisites:**

- 现有基于 `OPENROUTER_API_KEY` 的 LLM 调用路径已在当前环境下可用。

**Technical Notes:**

- 推荐在代码中封装一个 `OpenAICompatibleClient` 或等价抽象：
  - 内部持有 base_url、api_key、model 等配置；
  - 统一处理 header、超时与错误重试逻辑；
  - 对调用方暴露统一的 "chat_completion" 接口。  
- 需要注意部分提供商对扩展字段（如 `thinking`、`metadata` 等）的兼容性差异，必要时做降级或条件发送。

---

## FR Coverage Matrix

| FR ID  | Epic                                      | Stories             |
|-------|-------------------------------------------|---------------------|
| FR-L1 | Epic 1: 支持任意 OpenAI 协议兼容 LLM 提供商 | Story 1.1（初始版） |

---

## Summary

- 当前版本仅引入 1 个平台能力 Epic：统一支持任意 OpenAI 协议兼容 LLM 提供商，并通过 Story 1.1 覆盖最基础的「环境变量配置与切换」能力。  
- 后续可以在本文件中继续为该 Epic 增加更多 Stories（例如：错误监控与熔断、不同供应商性能对比、面向回测的单独 LLM 配置等），或新增其他独立 Epic。  
