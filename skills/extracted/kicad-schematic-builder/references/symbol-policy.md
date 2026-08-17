# KiCad 标准符号与自定义符号策略

## 核心原则

优先使用安装版本中的 KiCad 标准符号。`.kicad_sch` 的 `lib_symbols` 是符号缓存，不代表符号属于项目自定义库。

- 分立器件、电源、通用连接器、安装孔和测试点必须使用标准库。
- IC 存在准确型号或 KiCad `x` 通配型号时必须使用标准库。
- 标准库不存在准确型号时，才允许使用项目自定义符号。
- 复杂 IC 使用矩形本体属于正常画法；不得仅凭矩形外观判定不专业。
- 默认电阻风格为 IEC：`Device:R` 或 `Device:R_Small`。

## Gate 0 符号计划

方案表至少包含：

| Reference | Value | Planned lib_id | Source | Standard candidate | Custom reason |
|---|---|---|---|---|---|

在摆放前定位标准符号目录并检查候选。不要先生成简化符号，再把替换工作留到最终阶段。

## 严格审计

```powershell
python scripts/audit_schematic.py <project.kicad_sch> `
  --profile symbol `
  --output-dir <audit-dir> `
  --strict-symbol-policy
```

可选参数：

- `--kicad-symbol-dir`：显式指定标准 `.kicad_sym` 目录。
- `--symbol-policy`：覆盖技能默认策略 JSON。
- `--symbol-manifest`：指定项目自定义符号清单。
- `--symbol-report`：指定符号来源 JSON 输出路径。
- `--symbol-index-cache`：覆盖标准库索引缓存位置。
- `--no-symbol-index-cache`：禁用索引缓存并强制重建。

标准库目录按以下顺序查找：显式参数、`KICAD11/10/9_SYMBOL_DIR`、通用环境变量、`kicad-cli` 相对目录，以及 Windows、Linux、macOS 常见安装目录。索引默认缓存在用户本地 Codex 缓存目录，并按标准库文件元数据摘要失效。严格模式下无法定位标准库时必须失败。

## 判定规则

- `standard-symbol-required`：分立器件或连接器使用了项目自定义符号。
- `power-symbol-required`：电源对象没有使用 `power:*`。
- `standard-symbol-available`：标准库存在精确或 `x` 通配型号。
- `standard-symbol-candidate`：存在高相似度候选，需要人工判断。
- `embedded-custom-symbol`：符号只存在于原理图缓存，没有项目库声明。
- `custom-library-missing`：`sym-lib-table` 指向的项目库文件不存在。
- `custom-symbol-not-in-library`：项目库文件存在，但目标符号只残留在原理图缓存中。
- `custom-symbol-cache-mismatch`：项目 `.kicad_sym` 引脚定义与原理图 `lib_symbols` 缓存不一致，必须在 KiCad 中重新保存并复核。
- `custom-symbol-unregistered`：专用自定义符号未登记。
- `resistor-style-mismatch`：电阻图形不符合项目 IEC/US 风格。

所有上述未解决项都会阻止严格 Gate。已登记且质量检查通过的专用自定义符号可以通过。

## 自定义符号清单

项目旁使用 `<project>.symbol-manifest.json`：

```json
{
  "version": 1,
  "resistor_style": "iec",
  "approved_custom_symbols": {
    "FOC:DRV8353RSRGZR": {
      "reason": "KiCad 10 标准库不存在准确型号",
      "datasheet": "https://www.ti.com/lit/ds/symlink/drv8353.pdf",
      "pin_count": 49,
      "pins_reviewed": true,
      "footprint_reviewed": true
    }
  }
}
```

自定义符号必须满足：

- 由项目 `sym-lib-table` 指向真实 `.kicad_sym` 文件；
- 实例具有有效数据手册和封装；
- 清单引脚数与项目 `.kicad_sym` 源定义一致；
- 引脚号唯一，IC 引脚名和电气类型具有实际语义；
- 已完成引脚和封装人工审核。

原理图 `lib_symbols` 仅用于检查缓存一致性，不作为自定义符号质量审核的数据源。多单元或 De Morgan 变体中重复且完全相同的引脚定义允许存在；同一引脚号出现不同名称或电气类型时阻止通过。

标准库存在候选时不能普通登记豁免。只有 IC 类专用符号在用户明确确认后才能增加：

```json
{
  "override_standard_candidate": true,
  "override_reason": "用户确认使用经过验证的项目符号，原因是……"
}
```

该例外不能绕过分立器件、通用连接器、安装孔、测试点或 `power:*` 的强制标准库规则。最终交付必须在符号报告中列出该例外。

## 报告

默认生成 `<project>-symbols.json`，包含：

- 标准、项目自定义和仅缓存符号数量；
- 每个实例的 `reference/value/lib_id/source/status`；
- 推荐标准候选；
- 自定义符号质量检查；
- blocking findings 和已批准例外。
