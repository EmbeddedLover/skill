# Hellozhi MCP 页面记录

来源：[https://www.hellozhi.com/app/mcp-servers](https://www.hellozhi.com/app/mcp-servers)

采集日期：2026-08-09。页面显示 20 个 MCP 条目；以下只保留与 VibeBoard 硬件开发链路关系较强的候选。没有安装或运行任何 MCP。

| 优先级 | MCP | 可能用途 | 主要风险/前置检查 |
|---|---|---|---|
| P0 | [Espressif Docs MCP](https://mcp.espressif.com/docs) | ESP-IDF 官方资料检索 | 确认服务条款、可用性和返回内容版本 |
| P0 | [oraios/serena](https://github.com/oraios/serena) | 代码语义检索、项目上下文 | 工作区读写边界、索引隐私、许可证 |
| P0 | [upstash/context7](https://github.com/upstash/context7) | 当前技术文档上下文 | 来源可信度、版本固定、外部服务数据边界 |
| P1 | [mixelpixx/KiCAD-MCP-Server](https://github.com/mixelpixx/KiCAD-MCP-Server) | KiCad 工程操作 | EDA 文件写入、KiCad 版本、撤销/备份、许可证 |
| P1 | [lamaalrajih/kicad-mcp](https://github.com/lamaalrajih/kicad-mcp) | KiCad 工程操作 | 与其他 KiCad MCP 能力重叠，需实测选一 |
| P1 | [hyl64/jlcmcp](https://github.com/hyl64/jlcmcp) | 立创 EDA 工作流 | 登录状态、API 稳定性、项目写入和版权 |
| P1 | [coffeenmusic/altium-mcp](https://github.com/coffeenmusic/altium-mcp) | Altium 自动化 | Windows/Altium 版本、工程写入、商业许可 |
| P1 | [salitronic/eda-agent](https://github.com/salitronic/eda-agent) | EDA Agent 能力 | 支持格式、写入安全、维护活跃度 |
| P1 | [Averyy/pcbparts-mcp](https://github.com/Averyy/pcbparts-mcp) | 元器件/封装资料检索 | 参数来源、封装准确性、供应链实时性 |
| P2 | [github/github-mcp-server](https://github.com/github/github-mcp-server) | 仓库、Issue、PR 和代码协作 | Token 权限、外部写操作、组织数据范围 |

## 采用原则

- P0 先解决“证据从哪里来”和“如何理解现有工程”。
- P1 的 EDA/器件 MCP 必须做候选对比，不能同时全部接入。
- EDA 写操作需要快照、变更预览、用户确认和可回滚产物。
- MCP 返回内容仍需标记来源和时间，不能因为来自工具就自动视为已确认事实。
- 安装前必须核对许可证、最近维护时间、依赖树、网络访问、文件写入和凭证权限。
