# Hellozhi Skills 页面记录

来源：[https://www.hellozhi.com/app/skills](https://www.hellozhi.com/app/skills)

采集日期：2026-08-09。页面需要登录；本文件是用户授权登录会话中的结构化记录，不是网站镜像。

## 页面统计

- 页面共显示 53 个 Skills 条目。
- 其中 24 个提供直接 ZIP 下载。
- 本地已收齐全部 24 个直接下载包。
- 解压后共有 49 个 `SKILL.md`，因为 `embed-ai-tool` 一个包内包含总控、多个构建/烧录/调试子技能和一个模板。

## 已归档 ZIP

`NextBoard`、`chip-driver-manual`、`chip-resource-finder`、`embed-ai-tool`、`embedded-architecture-planner`、`embedded-bug-hunter`、`embedded-build-flash-debug`、`embedded-change-report`、`embedded-coding-standard`、`embedded-llm-guardrails`、`embedded-minimal-project-builder`、`embedded-prd-to-logic`、`embedded-production-test-tool`、`embedded-project-intake`、`embedded-project-scaffold`、`embedded-team-sync`、`embedded-unit-test-generator`、`kicad-schematic-builder`、`market-mrd-analyst`、`mrd-to-prd`、`parsed-chip-datasheet`、`prd-to-hardware-solution`、`schematic-pinmap-analyzer`、`vendor-minimal-firmware`。

## 页面反映出的能力分组

- 市场和需求：MRD、PRD、需求澄清、需求到业务逻辑。
- 硬件方案：架构候选、选型、电源树、接口矩阵、风险和验证计划。
- 硬件证据：Datasheet、芯片资料、原理图和 Pin Map。
- 固件接入：工程盘点、边界保护、架构规划、最小工程。
- 执行闭环：构建、烧录、串口、GDB、RTOS、总线和仪器分析。
- 质量交付：静态分析、单元测试、Bug 审计、变更报告、产测工具。

## 对 VibeBoard 的含义

页面上的 Skills 不应作为 53 个平级按钮呈现。用户说的是目标，不会先知道应该选哪个 Skill。VibeBoard 应把这些能力组织成一个有状态的编排器，通过当前项目画像、风险等级、缺失证据和上一步结果自动路由；只有存在影响硬件正确性的歧义时才向用户提问。
