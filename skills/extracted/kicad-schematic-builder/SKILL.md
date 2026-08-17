---
name: kicad-schematic-builder
description: Create, modify, wire, organize, repair, and validate KiCad schematic projects (.kicad_sch/.kicad_pro), especially MCU minimum systems and modular single-sheet designs. Use when Codex needs to build from requirements or a reference image, place symbols, add power/GND/net labels, route module-local wires, enforce KiCad standard-library symbols, audit custom-symbol provenance, repair ERC or visual-overlap issues, export previews/netlists, or perform a read-only schematic audit. Use staged user approvals for new designs and major relayouts, while allowing direct read-only audits and proportionate repair workflows. Do not use for EasyEDA-only operations or PCB layout/routing unless explicitly included.
---

# KiCad Schematic Builder

Produce valid engineering schematics with correct connectivity, professional standard symbols, readable layout, and reproducible validation.

## Select the task mode first

Choose one mode before reading optional references or editing files:

- **Create / major relayout**: use the full gated workflow.
- **Place only**: plan, place, validate, and stop after Gate 1.
- **Label**: confirm the net/power map, make the scoped change, and validate through Gate 2.
- **Wire**: confirm the connection map, route, and validate through Gates 3 and 4.
- **Repair**: diagnose first; request approval only when the fix changes topology, scope, or user-visible layout materially.
- **Audit**: inspect and report read-only without approval gates.

Do not expand schematic work into PCB layout, board routing, manufacturing output, or firmware without explicit scope.

## Read only the references needed

- For Create, major relayout, or reference-driven placement, view all schematic images supplied in the current request.
- View [assets/reference-modular-schematic.png](assets/reference-modular-schematic.png) and read [references/reference-layout.md](references/reference-layout.md) only when the user requests the bundled house style or no current layout reference exists.
- Apply this precedence: current text requirements, current uploaded schematic, explicitly selected bundled reference, then general layout heuristics.
- Before placement or final visual acceptance, read [references/visual-audit.md](references/visual-audit.md).
- Before selecting or approving symbols, read [references/symbol-policy.md](references/symbol-policy.md).
- For detailed wiring, coordinate, power-domain, ERC, and failure-mode guidance, read [references/workflow-and-failure-modes.md](references/workflow-and-failure-modes.md).

When a reference image is used, summarize what to inherit, adapt, and ignore. Never infer unrequested USB-C, CH340, OLED, RGB LED, automatic-download, or ESP32-specific circuits from the bundled image.

## Use proportionate approval gates

The user may explicitly request a one-pass implementation and waive pauses.

### Gate 0: approve the design plan

Use for Create, major relayout, and broad topology changes. Present:

- scope, exclusions, modules, and page partition;
- references, values, footprints, planned `lib_id`, source, standard candidate, and custom-symbol reason;
- power/functional net names and connector pin maps;
- outputs, validation criteria, and reference-image decisions.

Do not edit project files until approved.

### Gate 1: approve placement

Create a parseable project containing symbols, references, values, footprints, module frames, titles, and explanatory text only. Do not add electrical objects unless approved.

Run the placement profile, export an SVG separately, inspect the rendered preview, and stop for approval:

```powershell
python scripts/audit_schematic.py <project.kicad_sch> `
  --profile placement `
  --strict-symbol-policy `
  --fail-on-visual
```

Visual errors block this gate. Warnings require preview review; use `--fail-on-visual-warnings` only when the user requires zero-warning geometry.

### Gate 2: approve labels and power

Add canonical labels, power symbols, GND, and electrically justified `PWR_FLAG` objects. Use minimal label stubs only; do not route functional wiring yet. Re-run symbol provenance, export a preview, and provide the final net/power/connector map for approval.

### Gate 3: approve wiring

Draw short orthogonal module-local wires and connect modules through same-name labels. Run the full audit, ERC, netlist checks, and preview export. Stop with the wired preview and validation summary.

### Gate 4: final validation

Apply approved corrections, run strict final checks, regenerate previews, remove temporary generation files, and deliver. Do not accept unresolved visual errors or symbol-provenance blockers. Record any user-approved warning or custom-symbol exception.

## Build with stable engineering rules

- Inspect existing files and preserve unrelated projects or user changes.
- Confirm exact part number, package, power domains, clocks, reset, boot, debug, and connector mapping from requirements or authoritative data.
- Use installed KiCad standard symbols for discrete parts, power objects, generic connectors, mounting holes, test points, and ICs with accurate standard candidates.
- Treat schematic `lib_symbols` as a cache. Validate custom symbols against the real project `.kicad_sym` file declared by `sym-lib-table`.
- Use one canonical name per electrical net; normalize aliases before wiring.
- Keep the controller central, group support circuits by function, and reserve corridors for labels, wires, properties, frames, and the title block.
- Route with horizontal/vertical segments and exact transformed pin coordinates. Add junctions only at real branch points.
- Use `PWR_FLAG` only when the actual power source or isolated passive domain requires it.

Never trust visual contact alone: a wire endpoint must coincide exactly with the transformed KiCad pin endpoint.

## Run only the checks needed

The audit profiles avoid unrelated work:

```powershell
# Standard/custom symbol provenance only
python scripts/audit_schematic.py <project.kicad_sch> --profile symbol --strict-symbol-policy

# Geometry and wire-shape checks without standard-library scanning
python scripts/audit_schematic.py <project.kicad_sch> --profile visual --fail-on-visual

# Wire/ERC/netlist/SVG checks
python scripts/audit_schematic.py <project.kicad_sch> --profile electrical --require-cli

# Complete final acceptance
python scripts/audit_schematic.py <project.kicad_sch> `
  --profile full `
  --max-wire-mm 30 `
  --strict-symbol-policy `
  --fail-on-visual `
  --fail-on-visual-warnings `
  --render-png `
  --expect-net "SWDIO=U1:34,J2:2,J3:17"
```

Use `--checks symbol,visual,wires,cli` only when a custom combination is needed. Standard-library indexing is cached outside the project and invalidated when library file metadata changes.

## Validate and hand off

Before delivery, verify:

- KiCad opens and exports without missing symbols;
- references, values, footprints, ERC, and critical net membership are correct;
- symbol provenance has no blockers and project custom symbols match their source libraries;
- wires do not cross symbols, text, module frames, or the title block;
- visual warnings have been reviewed against the final SVG/PNG;
- generated previews match the final saved schematic.

Return links to requested project files and generated reports. Summarize electrical results, visual errors/warnings, critical nets, standard/custom symbol counts, approved exceptions, and intentionally excluded scope.
