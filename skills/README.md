# Skills 原始资料说明

## 清点结果

- 原始 ZIP：24 个。
- 解压目录：24 个顶层目录。
- `SKILL.md`：49 份。
- 可用技能定义：48 份。
- 模板占位：`embed-ai-tool/templates/skill-template/SKILL.md`。
- 解压文件总数：418。

24 个 ZIP 对应网站 Skills 页面上全部可直接下载的条目。最初附件中有 22 个；登录网站后补充下载了：

- `kicad-schematic-builder.zip`
- `NextBoard.zip`

## 安全检查

解压前后已检查：

- ZIP 完整性；
- `../` 路径穿越；
- 绝对路径；
- 符号链接；
- 解压目标是否限定在 `skills/extracted/`。

未执行任何压缩包内的 `.py`、`.sh`、`.mjs`、Hook、安装脚本或工具脚本。

## 原始内容与索引范围

以下内容保留在原始解压目录中，但不纳入推荐目录：

- `.pycache_root/`
- `__pycache__/`
- `*.pyc`
- `embed-ai-tool/.claude/settings.json`

它们没有被删除，以保持原始归档可追溯。后续引用时请使用 `analysis/skills-catalog.md`，不要把缓存和本地代理配置复制进 VibeBoard。

## 许可证状态

- `NextBoard`：`README.md` 和插件清单声明 MIT，但 ZIP 中没有独立 `LICENSE` 文件。
- `embedded-project-intake/assets/mermaid.min.js`：文件内部包含若干第三方组件的许可证提示；这不等于整个技能包获得同一许可证。
- 其余包：未发现 `LICENSE*`、`COPYING*`、`NOTICE*`，README 也未发现明确包级授权。

因此，除 `NextBoard` 的已声明内容外，所有材料先按“内部研究参考”处理。复制代码、模板或长篇原文进入 VibeBoard 前，需要逐包补做来源和授权核验。

## 校验

在本目录运行：

```bash
shasum -a 256 -c SHA256SUMS
```

`SHA256SUMS` 用于发现本地归档是否被改变，不证明发布者身份或供应链真实性。
