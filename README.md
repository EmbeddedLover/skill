# 小智学长硬件 AI 课程参考库

整理日期：2026-08-09

本目录保存课程文档、从 `hellozhi.com` 下载的原始 Skills、解压后的只读参考内容，以及面向 VibeBoard 的分析结论。原始资料与分析文件分层存放，后续优化 VibeBoard 时应优先阅读 `analysis/`，需要核对原文时再进入 `skills/extracted/`。

## 目录

- `AI编程-开发嵌入式单片机硬件产品-启航.md`：课程启航文档。
- `skills/*.zip`：24 个原始下载包，保持原样。
- `skills/extracted/`：经过安全检查后解压的原始内容。
- `skills/SHA256SUMS`：原始 ZIP 的 SHA-256 校验和。
- `web-reference/`：登录网站后整理的页面信息、Prompt 模式和 MCP 清单。
- `analysis/`：技能审计、VibeBoard 优先级和集成建议。

## 当前状态

- 网站 Skills 页面共显示 53 个条目，其中 24 个提供直接 ZIP 下载；24 个 ZIP 已全部收齐。
- 解压后共有 49 份 `SKILL.md`，其中 48 份是可用技能定义，1 份是模板占位文件。
- 所有 ZIP 均通过完整性、路径穿越、绝对路径和符号链接检查。
- 没有执行任何下载包中的脚本、安装器或 Hook。
- `NextBoard` 的 README 和插件清单声明 MIT；其余下载包未发现包级许可证文件或明确授权声明，应仅作内部研究参考。

## 使用入口

1. 先看 [VibeBoard 优先级](analysis/vibeboard-priority.md)。
2. 再看 [建议的集成状态机](analysis/integration-map.md)。
3. 查单个 Skill 时看 [技能目录](analysis/skills-catalog.md)。
4. 查网页内容时看 [网页参考资料](web-reference/site-workflows.md)。

## 安全边界

这些下载包不是当前项目的已审计依赖。后续不要直接整包安装或执行其中脚本，应先确认许可证、来源、依赖、写盘范围、外部命令、设备访问和回滚行为。烧录、擦除、Option Bytes/Fuse、串口 Shell 写操作及 EDA 文件写入必须使用独立确认门禁。
# xiaozhi-skills
