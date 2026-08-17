# 外设点亮台账 Skill

`embedded-bringup-logbook` 用于在拿到新开发板后逐个点亮外设（bring-up）的过程中，建立并持续维护一份可信的硬件台账。

核心作用是让**已被硬件验证过的事实**和**AI 或文档的推测**在文件层面彻底分开，从而解决两个高频问题：引脚复用冲突，以及 LLM 编造引脚号导致的长时间无效排查。

## 与相邻 skill 的区别

| Skill | 定位 |
|-------|------|
| `schematic-pinmap-analyzer` | 一次性分析原理图 PDF/图片，输出 IO 分配与驱动逻辑 |
| `embedded-bringup-logbook` | 持续维护的台账，随每个外设调通而增长 |
| `embedded-llm-guardrails` | 约束 LLM 在既有工程中的代码修改边界 |

前者是输入端的解析，本 skill 是过程中的沉淀。两者可以配合：用 `schematic-pinmap-analyzer` 得到初始 IO 表，再导入本 skill 的台账开始逐项验证。

## 产出文件

```text
docs/hardware/
├── PINMAP.md                  # 全局引脚分配表（必须唯一）
├── PITFALLS.md                # 通用坑清单（跨外设）
└── peripherals/
    └── <外设名>.md            # 用到才建
```

`PINMAP.md` 固定表头：

```text
外设 | 物理脚号 | GPIO号 | 复用功能 | 方向 | 电平域 | 板载占用风险 | 状态 | 证据 | 备注
```

`PITFALLS.md` 固定表头：

```text
分类 | 现象 | 根因 | 规则/对策 | 影响范围 | 证据 | 记录日期
```

## 六条核心规则

**引脚表全局唯一** — 引脚冲突本质是跨外设问题。拆分到各外设文档会导致两边各自声称占用同一引脚而无人发现。

**证据等级必须标注** — 每条记录带 `[实测]` / `[官方]` / `[推测]` 标记，不允许留空。只有实测能升级等级。

**写规格，不写日记** — 结论前置、可直接抄用。失败尝试转写成规则："GPIO37 不可用作 I2S 输入，已被板载摄像头占用"，而不是"我试了 GPIO37 不行"。

**版本与日期置于文件头部** — 缺少版本号的台账会在平台升级后静默变成误导信息。日期用绝对格式。

**不编造具体数值** — 引脚号、电压、地址、波特率、API 名一律不推测。缺失写 `待核对` 并注明查证途径。

**不主动创建空脚手架** — 用到哪个建哪个。空模板不会被填写，只会增加负担并稀释可信度。

## 典型流程

```text
刷固件跑通 LED 和串口（建立基准）
  → 建 PINMAP.md / PITFALLS.md 骨架
  → 分配引脚（过冲突检查清单）
  → 上电前物理检查
  → 跑官方例程
  → 改成自己要的
  → 回填台账，状态改已验证
  → 下一个外设
  → 组合验证（两两 → 全部）
  → 功能开发
```

## LLM 上下文导出

台账的主要用途之一。导出时只包含 `[实测]` 和 `[官方]` 条目，附带版本信息、禁用引脚清单和约束指令。

其中一条约束值得单独说明：要求 LLM 生成代码后列出用到的每个引脚及其来源行。它无法为编造的引脚指出来源，这样能把隐蔽的幻觉变成可核对的清单。

## 参考文件

| 文件 | 用途 |
|------|------|
| `references/document-spec.md` | 字段定义、三种编号的区别、证据等级判定 |
| `references/conflict-checks.md` | 12 项引脚冲突检查 |
| `references/preflight-checklist.md` | 上电前物理检查 |
| `references/integration-tests.md` | 组合验证项与顺序 |
| `references/llm-context-export.md` | 上下文导出规范 |

## 安装

Codex：

```bash
mkdir -p "$HOME/.codex/skills"
rm -rf "$HOME/.codex/skills/embedded-bringup-logbook"
cp -r embedded-bringup-logbook "$HOME/.codex/skills/"
```

## 边界

不做硬件设计、器件选型、BOM 成本、PCB 工艺、结构散热分析。
