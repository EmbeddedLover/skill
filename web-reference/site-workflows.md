# Hellozhi 网站工作流摘要

采集日期：2026-08-09。以下内容来自用户授权登录后的功能页观察，作为产品流程参考，不是页面完整复制。

## 已查看页面

- [工作区首页](https://www.hellozhi.com/app)
- [Skills](https://www.hellozhi.com/app/skills)
- [硬件 Prompt](https://www.hellozhi.com/app/hardware-prompts)
- [MCP Servers](https://www.hellozhi.com/app/mcp-servers)
- [MRD](https://www.hellozhi.com/app/market-mrd)
- [PRD](https://www.hellozhi.com/app/prd)
- [硬件方案](https://www.hellozhi.com/app/hardware-solution)
- [原理图识别](https://www.hellozhi.com/app/schematic-recognition)
- [电路识别](https://www.hellozhi.com/app/circuit-recognition)
- [Datasheet 识别](https://www.hellozhi.com/app/datasheet-recognition)

## MRD

输入产品想法后，流程覆盖机会对齐、TAM/SAM/SOM、技术和商业可行性、风险、合规、验证计划，并输出 `Go / No-Go / Explore` 决策。值得借鉴的是把市场事实、产品假设和验证动作分开，而不是直接从一句想法跳到实现。

## PRD

提供 MVP、完整版和研发交付版模式。智能硬件会扩展硬件、固件、生产、认证、质量和售后等章节。适合 VibeBoard 的模式是：先用 MVP 收敛第一个可验证硬件闭环，再逐步补全量产要求。

## 硬件方案

主要结构是 2-3 个架构候选、关键器件和替代、接口、电源树和功耗预算、PCB/EMC 约束、风险与验证计划。真正有价值的不是生成一份长报告，而是每个选择都有约束依据、替代方案和验证动作。

## 原理图和电路识别

输出重点包括：

- 电源路径和电压域；
- MCU/SoC 型号与资源；
- 时钟、复位、启动和下载调试；
- 完整 IO 表；
- 外设驱动逻辑和信号路径；
- 网表拓扑和待确认冲突。

VibeBoard 应把识别结果写入结构化 Hardware Facts，而不是只生成一段说明文字。

## Datasheet 识别

页面支持把 PDF 转成 Markdown/JSON，并可选 DOCX/HTML/LaTeX；解析能力包含 VLM/Pipeline、表格、公式和 OCR。与本地 `parsed-chip-datasheet` 和 `chip-driver-manual` 的组合很契合：前者负责定位结构化内容，后者负责交叉核验并形成驱动开发事实。

## 最值得复用的共同模式

1. 先形成约束和证据，再设计或写代码。
2. 明确区分已确认、推断、未知和冲突。
3. 每一阶段都有进入条件和退出证据。
4. 生成最小可验证增量，不追求一次性生成完整产品。
5. 把硬件观察结果写回项目画像，供下一轮复用。
