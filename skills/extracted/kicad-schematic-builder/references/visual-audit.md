# KiCad 自动视觉审计

## 目标

把“图纸能打开、ERC 正确”和“图纸清晰易读”作为两组独立验收条件。每次摆放完成后执行静态几何审计，最终交付时同时执行几何审计、ERC、网络表核对和 SVG/PNG 预览检查。

## 默认命令

摆放阶段不要求电气连接完整：

```powershell
python scripts/audit_schematic.py <project.kicad_sch> `
  --profile placement `
  --output-dir <placement-audit-dir> `
  --fail-on-visual
```

`placement` profile 运行符号、线段和静态几何检查，但不执行 ERC、网络表和 SVG/PNG 导出。Gate 1 仍需另行执行 `kicad-cli sch export svg` 并查看最终预览；静态包围盒检查不能代替渲染后的人工确认。

连线完成后：

```powershell
python scripts/audit_schematic.py <project.kicad_sch> `
  --profile full `
  --output-dir <final-audit-dir> `
  --max-wire-mm 30 `
  --fail-on-visual `
  --fail-on-visual-warnings `
  --render-png
```

## 确定性检查

- `duplicate-wire`：同一坐标的线段被重复保存。
- `symbol-overlap`：两个器件图形边界实际重叠。
- `symbol-clearance`：器件边界间距小于 `--symbol-clearance-mm`，默认 1.27 mm。
- `text-collision`：可见属性、普通文字或网络标签互相碰撞或间距不足。
- `text-symbol-collision`：可见文字进入器件图形边界。
- `wire-through-symbol`：导线进入器件本体，不把“看起来接触”误当作合法连接。
- `wire-through-text`：导线穿过可见文字；标签自身的连接锚点允许接线。
- `wire-crosses-module-frame`：导线接触或穿越模块边框。
- `module-frame-through-content`：模块边框穿过器件或文字。
- `module-boundary-clearance`：模块内容离边框小于 `--module-clearance-mm`，默认 1.27 mm。
- `page-boundary-clearance`：内容进入页面安全边距，默认 5 mm。
- `title-block-intrusion`：器件或文字进入右下角标题栏预留区域。
- `module-frame-title-block-intrusion`：模块边框侵入标题栏。

只有 KiCad 实际可见的属性和文字参与碰撞检查；`effects` 中标记为 `hide yes` 的 Footprint、Datasheet、Description 等字段必须忽略。

模块边框从顶层大矩形、闭合折线或四条首尾连接的水平/垂直折线识别。默认只把面积不小于 180 mm2 的图形视为模块边框，避免把普通图形误判为模块。

## 视觉密度

审计器使用 2.54 mm 网格估算器件、文字和导线占用面积，并输出：

- 每个模块的 `occupied_ratio`；
- 每 1000 mm2 的项目数量；
- A4 页面六个区域的局部占用率。

默认模块占用率上限为 62%，页面区域上限为 72%。密度告警不是确定性错误，只有使用 `--fail-on-visual-warnings` 时才阻止通过。

## 结果解释

脚本输出控制台摘要和 `<project>-visual.json`。JSON 报告记录规则、严重级别、对象名称、坐标、阈值及各模块密度，优先按以下顺序修复：

1. 器件重叠、导线穿器件、边框穿越、标题栏侵入；
2. 文字碰撞、文字压线、标签遮挡；
3. 器件与边框间距；
4. 模块和页面区域密度。

`--fail-on-visual` 只阻止确定性 error；`--fail-on-visual-warnings` 额外阻止 warning。文字边界基于 KiCad 字号、对齐方式、旋转角度和中英文字符宽度估算，故意保留少量安全余量。出现临界告警时必须核对最终 PNG；只有确认属于字体估算余量而非真实碰撞后，才能小幅调整 `--text-clearance-mm`。不得因为告警数量较多而整体关闭视觉审计。

标题栏默认按右下角 115 mm x 40 mm 预留。使用自定义纸张或自定义标题栏时，通过 `--title-block-width-mm` 和 `--title-block-height-mm` 设置实际尺寸。

技能内中文 Markdown 使用 UTF-8。Windows PowerShell 5.1 直接读取时使用 `Get-Content -Encoding utf8`，避免控制台默认编码造成乱码。
