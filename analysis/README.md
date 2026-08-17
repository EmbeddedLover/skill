# 分析入口

## 结论

这些 Skills 最有价值的不是单个脚本，而是共同形成了一套嵌入式 Agent 方法：证据优先、事实分级、修改边界、最小可验证增量、真实硬件反馈和阶段交接。

VibeBoard 不应把 48 个可用技能逐个安装并直接暴露给用户。更合适的实现是一个统一的硬件开发状态机，下面挂接资料解析、项目接入、生成、构建、烧录、观测和诊断适配器。

## 文件

- [技能目录](skills-catalog.md)：24 个下载包和 `embed-ai-tool` 子技能的用途、优先级与注意事项。
- [VibeBoard 优先级](vibeboard-priority.md)：P0/P1/P2 建议、需要改写的规则和成功指标。
- [集成状态机](integration-map.md)：建议的数据合同、执行阶段、风险门禁和 Skill 映射。

## 优先阅读顺序

1. `vibeboard-priority.md`
2. `integration-map.md`
3. `skills-catalog.md`
4. 需要核对时再进入 `../skills/extracted/<package>/`

## 资料状态

- 已审阅全部 49 份 `SKILL.md`。
- 已重点核对 Guardrails、Project Intake、Scaffold 澄清门、芯片手册 Schema/来源核验、KiCad 符号与视觉门禁、NextBoard 方案验证门。
- 未执行下载包代码。
- 未修改 VibeBoard。
