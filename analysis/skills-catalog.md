# Skills 审计目录

优先级含义：

- `P0`：高成功率自然语言硬件开发的核心能力，应吸收设计思想并重写为 VibeBoard 原生能力。
- `P1`：P0 闭环稳定后接入的专业能力或工具适配器。
- `P2`：按用户/团队场景启用，不进入首版主路径。
- `R`：只保留原始参考，不作为可调用能力。

## 24 个下载包

| 包 | 优先级 | 对 VibeBoard 的价值 | 采用注意事项 |
|---|---|---|---|
| `embedded-llm-guardrails` | P0 | Allowed Files、生成代码保护、已验证代码保护、最小验证闭环 | 改成风险分级确认，避免所有改动都无条件暂停 |
| `embedded-project-intake` | P0 | 从现有工程建立证据化 Project Profile | 保留 `CONFIRMED/INFERRED/UNKNOWN/CONFLICT/UNVERIFIED` |
| `chip-resource-finder` | P0 | 找 Datasheet、Errata、SDK、示例和工具链 | 官方原厂和精确版本优先，记录抓取日期 |
| `chip-driver-manual` | P0 | 从手册/SDK/头文件提取寄存器、时序、初始化和约束 | 使用结构化 Schema；冲突影响硬件安全时阻塞生成 |
| `parsed-chip-datasheet` | P0 | 快速查询已解析手册 Bundle | 只负责定位，不替代来源核验 |
| `schematic-pinmap-analyzer` | P0 | 从原理图提取电源、MCU、IO、驱动逻辑和待确认项 | 图像识别结论默认需证据级别和人工/网表复核 |
| `embedded-prd-to-logic` | P0 | 把自然语言需求转为行为、状态机和最小任务 | 保持在应用逻辑层，不越权猜驱动和寄存器 |
| `embedded-architecture-planner` | P0 | 固件分层、任务、事件、接口和迁移计划 | 先输出接口合同，避免一次生成大量空骨架 |
| `embedded-project-scaffold` | P0 | 根据官方资料构建最小可构建工程 | 精确 MCU/板卡/时钟/引脚/工具链不明确时必须阻塞 |
| `vendor-minimal-firmware` | P0 | 从官方示例裁剪最小固件，保留启动/链接/工程配置 | 优先于“凭模型从零创建”启动工程 |
| `embedded-build-flash-debug` | P0 | 统一 build/flash/debug 入口与产物发现 | 烧录和调试必须绑定显式目标、探针和产物 |
| `embedded-unit-test-generator` | P0 | 用例矩阵、框架选择、Mock/Stub 和结果汇总 | 主机测试不能冒充板级验证 |
| `embedded-bug-hunter` | P0 | 竞态、ISR、DMA、状态机、存储和协议风险审计 | 保持读模式，输出证据和严重级别 |
| `embedded-change-report` | P0 | 汇总 Diff、构建、测试、日志和硬件验证证据 | 可作为每次 Agent Run 的最终审计产物 |
| `NextBoard` / `hardware-solution` | P1 | 需求冻结、三类架构、选型、风险、验证门和独立评审 | Datasheet 下载顺序存在冲突，必须改为官方/Errata 优先 |
| `prd-to-hardware-solution` | P1 | PRD 到系统框图、选型、电源、BOM、PCB 和验证 | 与 NextBoard 重叠，应合并成一个方案引擎 |
| `kicad-schematic-builder` | P1 | KiCad 标准符号、增量构建、ERC/网表/视觉独立门禁 | 写 EDA 文件前做版本、库和回滚确认 |
| `embed-ai-tool` | P1 | 多构建/烧录/调试工具的适配器集合 | 不整包直装；逐个审计适配器并统一结果 Schema |
| `embedded-coding-standard` | P1 | 项目规范、MISRA/CERT/BARR-C/RTOS 审查 | 不能捏造条款，合规结论需对应规则和工具证据 |
| `embedded-minimal-project-builder` | P1 | 为 AI 长期接管整理标准仓库、文档和索引 | 与 Scaffold 分工：前者管仓库合同，后者管可构建固件 |
| `market-mrd-analyst` | P1 | 市场机会、证据、TAM/SAM/SOM、Go/No-Go | 对“从想法做产品”有用，不应阻塞纯固件任务 |
| `mrd-to-prd` | P1 | MRD 到 MVP/完整/研发交付 PRD | 可作为产品模式入口，非开发模式必经步骤 |
| `embedded-production-test-tool` | P2 | PySide6 桌面工具脚手架 | 只是通用 GUI Scaffold，不等于产测方案或治具协议 |
| `embedded-team-sync` | P2 | `.ai/` 团队规则、状态、Registry 和任务日志 | VibeBoard 已有运行记录时避免重复维护第二套状态 |

## `embed-ai-tool` 内部技能

压缩包内共有 26 份 `SKILL.md`：1 个总控、24 个实际工具技能和 1 个模板。

| 分组 | 技能 | 建议 |
|---|---|---|
| 构建 | `build-cmake`、`build-makefile`、`build-keil`、`build-iar`、`build-idf`、`build-platformio` | P1 适配器；输出统一 Artifact Manifest |
| 烧录 | `flash-openocd`、`flash-jlink`、`flash-keil`、`flash-idf`、`flash-platformio` | P1；属于硬件写操作，必须确认 Target/Probe/Artifact |
| 在线调试 | `debug-gdb-openocd`、`debug-jlink`、`debug-platformio`、`rtos-debug` | P1；必须使用匹配 ELF 和明确设备配置 |
| 串口 | `serial-monitor`、`serial-shell` | Monitor 可进 P0 观测闭环；Shell 写命令按高风险处理 |
| 协议 | `can-debug`、`modbus-debug` | P1；发送/写寄存器和扫描操作需单独风险分类 |
| 仪器 | `logic-analyzer`、`visa-debug` | P1；把波形/测量结果写成结构化 Evidence |
| 分析 | `memory-analysis`、`static-analysis` | P1；可在构建后自动运行，不涉及硬件写入 |
| 编排 | `workflow`、`embed-ai-tool` | 只参考路由思想；VibeBoard 应自己实现统一状态机 |
| 模板 | `your-skill-name` | R；不是实际 Skill |

## 最可复用的具体设计

- Project Profile：持续保存 MCU、板卡、构建系统、产物、探针、串口、RTOS 和证据来源。
- Evidence Labels：关键事实必须带状态和来源，README/目录名不能单独确认硬件事实。
- Clarification Gate：精确型号、封装、内存、时钟、电压、引脚、烧录范围和探针不能猜。
- Guardrails：厂商 SDK、生成器输出、启动/链接、ISR、时序和已上板代码默认保护。
- Failure Taxonomy：环境缺失、产物缺失、连接失败、配置错误、目标异常、上下文歧义等统一分流。
- Handoff Contract：每个工具返回状态、证据、更新后的 Profile 和下一候选动作。
- Visual + Electrical Gates：KiCad 的可解析、ERC、网表和视觉审计是不同维度，不能互相替代。

## 已发现的问题

1. `NextBoard` 的 `design-workflow.md` 要求先尝试 AllDatasheet，晚于聚合站才查原厂；但其 Gate 和 `sourcing-and-risk.md` 又要求原厂优先。VibeBoard 应固定为精确版本 Errata/PCN、原厂手册、授权分销商、聚合站线索的顺序。
2. `flash-openocd` 的自动探测可能选择第一个探针，和更安全的显式确认规则冲突。VibeBoard 不能在多个候选时静默选择。
3. Guardrails 要求所有源码修改都先停下等待确认。对消费级产品会过度打断，应按读操作、可逆文件修改、构建、硬件写入、不可逆配置分级。
4. `embed-ai-tool` 中发现 4 处指向作者本机 `/home/leo/...` 的绝对参考路径，分布在 `CONTRIBUTING.md`、`shared/contracts.md` 和 `serial-monitor/SKILL.md`，说明该包的可移植性需要修复。
5. 多个技能都定义自己的流程和状态字段，直接叠加会产生冲突；需要一个 VibeBoard 原生 Schema 和状态机。
