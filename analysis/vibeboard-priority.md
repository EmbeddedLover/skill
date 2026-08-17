# VibeBoard 采用优先级

## 核心判断

要提高“自然语言开发硬件”的成功率，VibeBoard 的第一目标不应是生成更多代码，而应是降低错误假设进入执行链路的概率。最重要的产品能力是：把一句自然语言持续收敛为有证据、有边界、有验收标准的最小硬件任务，并用真实构建和板级反馈驱动下一步。

## P0：先构建闭环

### 1. Hardware Project Profile

吸收：`embedded-project-intake`、`chip-resource-finder`、`chip-driver-manual`、`parsed-chip-datasheet`、`schematic-pinmap-analyzer`。

Profile 至少保存：

- 精确 MCU/SoC、变体、封装、Flash/RAM；
- 板卡/自定义板、原理图和 Pin Map；
- 时钟、电压域、关键极性和启动配置；
- SDK/HAL/RTOS、工具链、构建系统；
- 构建/烧录/调试入口；
- 探针、串口和可用仪器；
- 每个事实的状态、来源、版本和抓取时间。

没有 Profile 或关键事实处于 `UNKNOWN/CONFLICT` 时，不进入可能损坏硬件或静默失败的步骤。

### 2. Risk-Aware Clarification

吸收：`embedded-project-scaffold` 的澄清门、`embedded-llm-guardrails` 的边界规则、Prompt 库的需求冻结模式。

只问当前步骤真正阻塞的问题。问题分两类：

- 可从工程/文档确定：Agent 自己读取，不询问用户。
- 影响硬件正确性且无法确定：给出候选、影响和推荐，让用户确认。

绝不猜测：精确料号、内存布局、启动文件、晶振/PLL、电压、引脚/AF、极性、擦写范围、Fuse/Option Bytes、探针、串口和目标板。

### 3. Minimal Verifiable Task

吸收：`embedded-prd-to-logic`、`embedded-architecture-planner`、`vendor-minimal-firmware`、`embedded-project-scaffold`。

把“做一个温湿度设备”拆成可独立验证的序列，例如：

1. 官方示例工程可构建；
2. 串口启动日志可见；
3. I2C 扫描/WHOAMI 成功；
4. 固定周期读原始值；
5. 单位换算和异常恢复；
6. 再接入状态机、云端或低功耗。

每一步先定义 Pass/Fail、观察点和回滚，再生成刚好够用的修改。

### 4. Build -> Flash -> Observe

吸收：`embedded-build-flash-debug`、`embed-ai-tool` 的构建/烧录适配器、`serial-monitor`。

- Build 自动化：可默认执行，保存命令、退出码、日志和 Artifact Manifest。
- Flash：明确目标、探针、产物、地址和复位策略后再执行。
- Observe：先打开串口/日志捕获再复位，避免丢失早期启动证据。
- 完成判断：不能把“生成成功”或“编译成功”当作硬件功能成功。

### 5. Diagnose -> Verify -> Report

吸收：`embedded-bug-hunter`、`embedded-unit-test-generator`、`embedded-change-report`，以及 GDB/RTOS/逻辑分析仪/仪器技能的输出合同。

失败后保留已验证最小功能，不继续堆修改。下一轮根据失败类别选择一个最小诊断动作，并把日志、寄存器、波形、测量或测试结果写回 Evidence Store。

## P1：闭环稳定后增强

- `NextBoard` + `prd-to-hardware-solution`：合并为方案设计引擎，输出架构候选、关键选型、电源树、接口矩阵、风险和 EVT/DVT/PVT。
- `kicad-schematic-builder`：用于原理图生成/修复；强制符号来源、ERC、网表和视觉四类验收。
- GDB/J-Link/OpenOCD/PlatformIO/RTOS 调试：处理崩溃、寄存器和线程级问题。
- `logic-analyzer`、`visa-debug`、`can-debug`、`modbus-debug`：把硬件观测扩展到信号、仪器和协议层。
- `memory-analysis`、`static-analysis`、`embedded-coding-standard`：构建后的自动质量门。
- `market-mrd-analyst`、`mrd-to-prd`：只在“从产品想法开始”模式启用。

## P2：按场景启用

- `embedded-production-test-tool`：适合生成桌面工具骨架，但不代表产测方案已完成。
- `embedded-team-sync`：多人仓库协同时使用，避免与 VibeBoard 自身运行状态重复。
- 串口 Shell 批量命令：可写设备状态，默认不进入自动流程。

## 需要重写，不能照搬

### 来源优先级

统一规则应是：精确硅版本 Errata/PCN -> 原厂 Reference Manual/Datasheet -> 原厂结构化文件和 SDK -> 授权分销商 -> 板级资料 -> 第三方聚合站/示例。聚合站适合发现线索，不适合作为硬件安全参数的最终证据。

### 确认策略

不要照搬“每次改文件都暂停”的规则。建议按风险等级：

- L0：读取、搜索、解析、静态分析，可自动执行。
- L1：在允许目录内做可逆文件修改、构建、主机测试，可在任务授权内自动执行并展示 Diff。
- L2：烧录、设备命令、EDA 写入、测试仪器输出，执行前确认精确目标和动作。
- L3：擦除范围、Fuse/Option Bytes、Bootloader/分区、校准/生产参数、可能损坏硬件的电源动作，必须逐次显式确认并提供回滚/恢复说明。

### Skill 编排

不能把多个 Skill 的自然语言输出直接串起来。应定义统一 JSON Schema，让每个能力只读取和更新明确字段；路由器根据状态和失败分类决定下一步。

### 脚本可信度

当前材料多数没有许可证，且脚本未做代码级安全审计。首版应重写关键适配器或只参考流程，不应把下载包直接作为生产执行代码。

## 推荐实施顺序

1. 统一 `Project Profile + Evidence + Risk Gate + Run State` Schema。
2. 接通现有项目 Intake、需求收敛、Allowed Files 和最小验证计划。
3. 接通一个黄金平台的 Build/Flash/Serial 闭环，例如 ESP-IDF 或 PlatformIO。
4. 加入失败分类、恢复点和 Change Report。
5. 用真实开发板任务做评测，再扩展 Keil/OpenOCD/J-Link、Datasheet、原理图和仪器能力。

## 成功指标

不要只评估模型回复质量。建议至少记录：

- 首次构建成功率；
- 首次烧录成功率；
- 首个板级验收通过率；
- 因错误硬件假设导致的失败率；
- 从失败到下一条有效诊断动作的命中率；
- 用户需要回答的问题数；
- 对厂商/生成器/已验证代码的误改次数；
- 每个结论有可追溯证据的比例；
- 回滚成功率和重复运行的一致性。

首批评测应覆盖：LED、UART、I2C WHOAMI、SPI JEDEC ID、ADC 读取、RTOS 任务、HardFault、错误晶振/引脚、多个串口/探针、Datasheet 冲突和烧录失败。
