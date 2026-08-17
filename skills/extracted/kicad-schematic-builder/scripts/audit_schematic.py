#!/usr/bin/env python3
"""Audit KiCad schematic connectivity, geometry, readability, and visual density."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata
from typing import Sequence

from kicad_sexpr import SExpr, atom, child, children, node_name, parse as parse_sexpr, recursive_nodes

from symbol_policy import (
    SymbolRecord,
    build_standard_index,
    evaluate_symbol_policy,
    load_json,
    locate_standard_symbol_dir,
    parse_project_libraries,
    pin_definition,
)


EPSILON = 1e-6
PAGE_SIZES_MM = {
    "A5": (210.0, 148.0),
    "A4": (297.0, 210.0),
    "A3": (420.0, 297.0),
    "A2": (594.0, 420.0),
    "A1": (841.0, 594.0),
    "A0": (1189.0, 841.0),
    "Letter": (279.4, 215.9),
    "Legal": (355.6, 215.9),
    "Ledger": (431.8, 279.4),
}
AUDIT_CHECKS = frozenset({"symbol", "visual", "wires", "cli"})
PROFILE_CHECKS = {
    "full": AUDIT_CHECKS,
    "placement": frozenset({"symbol", "visual", "wires"}),
    "symbol": frozenset({"symbol"}),
    "visual": frozenset({"visual", "wires"}),
    "electrical": frozenset({"wires", "cli"}),
}


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Box:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> Point:
        return Point((self.left + self.right) / 2, (self.top + self.bottom) / 2)

    def expanded(self, distance: float) -> "Box":
        return Box(self.left - distance, self.top - distance, self.right + distance, self.bottom + distance)

    def contains_point(self, point: Point, inset: float = 0.0) -> bool:
        return (
            self.left + inset - EPSILON <= point.x <= self.right - inset + EPSILON
            and self.top + inset - EPSILON <= point.y <= self.bottom - inset + EPSILON
        )

    def contains_box(self, other: "Box", inset: float = 0.0) -> bool:
        return (
            other.left >= self.left + inset - EPSILON
            and other.right <= self.right - inset + EPSILON
            and other.top >= self.top + inset - EPSILON
            and other.bottom <= self.bottom - inset + EPSILON
        )


@dataclass(frozen=True)
class Wire:
    start: Point
    end: Point
    identity: str

    @property
    def length(self) -> float:
        return math.hypot(self.end.x - self.start.x, self.end.y - self.start.y)

    @property
    def orthogonal(self) -> bool:
        return abs(self.start.x - self.end.x) < EPSILON or abs(self.start.y - self.end.y) < EPSILON

    @property
    def zero_length(self) -> bool:
        return self.length < EPSILON

    @property
    def box(self) -> Box:
        return box_from_points([self.start, self.end])


@dataclass(frozen=True)
class VisualItem:
    kind: str
    identity: str
    box: Box
    anchor: Point | None = None
    owner: str | None = None


@dataclass(frozen=True)
class Frame:
    identity: str
    box: Box


@dataclass(frozen=True)
class Issue:
    rule: str
    severity: str
    message: str
    objects: tuple[str, ...]
    location: tuple[float, float] | None = None


def visual_gate_failures(
    issues: Sequence[Issue], fail_errors: bool, fail_warnings: bool
) -> list[str]:
    failures: list[str] = []
    if fail_errors and any(issue.severity == "error" for issue in issues):
        failures.append("visual errors found")
    if fail_warnings and any(issue.severity == "warning" for issue in issues):
        failures.append("visual warnings found")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schematic", type=Path, help="Path to a .kicad_sch file")
    parser.add_argument("--profile", choices=sorted(PROFILE_CHECKS), default="full", help="Select a predefined audit scope")
    parser.add_argument("--checks", help="Comma-separated checks overriding --profile: symbol,visual,wires,cli")
    parser.add_argument("--kicad-cli", type=Path, help="Path to kicad-cli executable")
    parser.add_argument("--output-dir", type=Path, help="Directory for reports, ERC, netlist, and SVG outputs")
    parser.add_argument("--max-wire-mm", type=float, help="Fail when a wire segment exceeds this length")
    parser.add_argument("--text-clearance-mm", type=float, default=0.35, help="Minimum text clearance")
    parser.add_argument("--symbol-clearance-mm", type=float, default=1.27, help="Minimum body-to-body clearance")
    parser.add_argument("--module-clearance-mm", type=float, default=1.27, help="Minimum content clearance to module border")
    parser.add_argument("--page-margin-mm", type=float, default=5.0, help="Minimum content clearance to page edge")
    parser.add_argument("--min-frame-area-mm2", type=float, default=180.0, help="Minimum rectangle area treated as a module frame")
    parser.add_argument("--density-cell-mm", type=float, default=2.54, help="Grid cell size used for density estimation")
    parser.add_argument("--max-module-density", type=float, default=0.62, help="Warn when occupied module area ratio exceeds this value")
    parser.add_argument("--max-zone-density", type=float, default=0.72, help="Warn when a page-zone occupied ratio exceeds this value")
    parser.add_argument("--max-items-per-1000mm2", type=float, default=55.0, help="Warn when module item count exceeds this density")
    parser.add_argument("--title-block-width-mm", type=float, default=115.0, help="Reserved title-block width")
    parser.add_argument("--title-block-height-mm", type=float, default=40.0, help="Reserved title-block height")
    parser.add_argument("--max-reported-issues", type=int, default=120, help="Maximum findings per audit category printed to the console")
    parser.add_argument("--fail-on-visual", action="store_true", help="Fail on visual errors")
    parser.add_argument("--fail-on-visual-warnings", action="store_true", help="Fail on visual errors and heuristic warnings")
    parser.add_argument("--visual-report", type=Path, help="Write visual audit details as JSON")
    parser.add_argument("--kicad-symbol-dir", type=Path, help="Directory containing KiCad standard .kicad_sym files")
    parser.add_argument("--symbol-policy", type=Path, help="Standard-symbol policy JSON")
    parser.add_argument("--symbol-manifest", type=Path, help="Project-approved custom-symbol manifest JSON")
    parser.add_argument("--symbol-report", type=Path, help="Write symbol provenance audit details as JSON")
    parser.add_argument("--symbol-index-cache", type=Path, help="Override the standard-symbol index cache file")
    parser.add_argument("--no-symbol-index-cache", action="store_true", help="Disable the standard-symbol index cache")
    parser.add_argument(
        "--strict-symbol-policy",
        action="store_true",
        help="Fail on standard-symbol violations and unresolved custom-symbol findings",
    )
    parser.add_argument(
        "--expect-net",
        action="append",
        default=[],
        metavar="NET=REF:PIN,REF:PIN",
        help="Require nodes to appear on a named net; may be repeated",
    )
    parser.add_argument("--allow-erc-warnings", action="store_true", help="Do not fail on ERC warnings")
    parser.add_argument("--render-png", action="store_true", help="Render the exported SVG with cairosvg")
    parser.add_argument("--require-cli", action="store_true", help="Fail if kicad-cli cannot be located")
    parser.add_argument("--skip-cli", action="store_true", help="Remove the cli check from the selected profile")
    return parser.parse_args()


def resolve_checks(args: argparse.Namespace) -> frozenset[str]:
    checks = set(PROFILE_CHECKS[args.profile])
    if args.checks:
        checks = {item.strip().lower() for item in args.checks.split(",") if item.strip()}
        invalid = sorted(checks - AUDIT_CHECKS)
        if invalid:
            raise ValueError(f"Unknown audit checks: {', '.join(invalid)}")
    if args.skip_cli:
        checks.discard("cli")
    if args.strict_symbol_policy:
        checks.add("symbol")
    if args.symbol_report:
        checks.add("symbol")
    if args.fail_on_visual or args.fail_on_visual_warnings or args.visual_report:
        checks.add("visual")
    if args.max_wire_mm is not None:
        checks.add("wires")
    if args.expect_net or args.render_png or args.require_cli:
        checks.add("cli")
    return frozenset(checks)


def locate_kicad_cli(explicit: Path | None) -> Path | None:
    if explicit:
        return explicit.resolve()
    discovered = shutil.which("kicad-cli")
    if discovered:
        return Path(discovered)
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    candidates = [
        program_files / "KiCad" / "11.0" / "bin" / "kicad-cli.exe",
        program_files / "KiCad" / "10.0" / "bin" / "kicad-cli.exe",
        program_files / "KiCad" / "9.0" / "bin" / "kicad-cli.exe",
        Path(r"D:\softwave\bin\kicad-cli.exe"),
        Path("/usr/bin/kicad-cli"),
        Path("/usr/local/bin/kicad-cli"),
        Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"),
    ]
    return next((path for path in candidates if path.exists()), None)


def number(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def point_from(node: Sequence[SExpr] | None, start_index: int = 1) -> Point:
    return Point(number(atom(node, start_index)), number(atom(node, start_index + 1)))


def at_from(node: Sequence[SExpr]) -> tuple[Point, float]:
    at = child(node, "at")
    return point_from(at), number(atom(at, 3))


def uuid_from(node: Sequence[SExpr], fallback: str) -> str:
    value = atom(child(node, "uuid"), 1)
    return value[:8] if value else fallback


def box_from_points(points: Sequence[Point]) -> Box:
    return Box(
        min(point.x for point in points),
        min(point.y for point in points),
        max(point.x for point in points),
        max(point.y for point in points),
    )


def boxes_overlap(first: Box, second: Box, clearance: float = 0.0) -> bool:
    distance = clearance / 2
    first = first.expanded(distance)
    second = second.expanded(distance)
    return not (
        first.right <= second.left + EPSILON
        or second.right <= first.left + EPSILON
        or first.bottom <= second.top + EPSILON
        or second.bottom <= first.top + EPSILON
    )


def overlap_center(first: Box, second: Box) -> tuple[float, float]:
    return (
        (max(first.left, second.left) + min(first.right, second.right)) / 2,
        (max(first.top, second.top) + min(first.bottom, second.bottom)) / 2,
    )


def segment_intersects_box(wire: Wire, box: Box, inset: float = 0.0) -> bool:
    target = Box(box.left + inset, box.top + inset, box.right - inset, box.bottom - inset)
    if target.width <= 0 or target.height <= 0:
        return False
    x1, y1, x2, y2 = wire.start.x, wire.start.y, wire.end.x, wire.end.y
    dx, dy = x2 - x1, y2 - y1
    p = (-dx, dx, -dy, dy)
    q = (x1 - target.left, target.right - x1, y1 - target.top, target.bottom - y1)
    lower, upper = 0.0, 1.0
    for direction, distance in zip(p, q):
        if abs(direction) < EPSILON:
            if distance < 0:
                return False
            continue
        ratio = distance / direction
        if direction < 0:
            lower = max(lower, ratio)
        else:
            upper = min(upper, ratio)
        if lower > upper:
            return False
    return True


def segment_box_intersection_location(wire: Wire, box: Box) -> tuple[float, float]:
    if abs(wire.start.y - wire.end.y) < EPSILON:
        left = max(min(wire.start.x, wire.end.x), box.left)
        right = min(max(wire.start.x, wire.end.x), box.right)
        return ((left + right) / 2, wire.start.y)
    if abs(wire.start.x - wire.end.x) < EPSILON:
        top = max(min(wire.start.y, wire.end.y), box.top)
        bottom = min(max(wire.start.y, wire.end.y), box.bottom)
        return (wire.start.x, (top + bottom) / 2)
    return (box.center.x, box.center.y)


def segments_intersect(first: Wire, second: Wire) -> bool:
    def orientation(a: Point, b: Point, c: Point) -> float:
        return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)

    def on_segment(a: Point, b: Point, c: Point) -> bool:
        return (
            min(a.x, c.x) - EPSILON <= b.x <= max(a.x, c.x) + EPSILON
            and min(a.y, c.y) - EPSILON <= b.y <= max(a.y, c.y) + EPSILON
        )

    a, b, c, d = first.start, first.end, second.start, second.end
    o1, o2, o3, o4 = orientation(a, b, c), orientation(a, b, d), orientation(c, d, a), orientation(c, d, b)
    if ((o1 > EPSILON and o2 < -EPSILON) or (o1 < -EPSILON and o2 > EPSILON)) and (
        (o3 > EPSILON and o4 < -EPSILON) or (o3 < -EPSILON and o4 > EPSILON)
    ):
        return True
    return any(
        abs(value) < EPSILON and on_segment(start, point, end)
        for value, start, point, end in (
            (o1, a, c, b),
            (o2, a, d, b),
            (o3, c, a, d),
            (o4, c, b, d),
        )
    )


def visible(node: Sequence[SExpr]) -> bool:
    effects = child(node, "effects")
    hide = child(node, "hide") or (child(effects, "hide") if effects else None)
    return not (hide is not None and atom(hide, 1, "yes") == "yes")


def effects_data(node: Sequence[SExpr]) -> tuple[float, float, set[str]]:
    effects = child(node, "effects")
    font = child(effects, "font") if effects else None
    size = child(font, "size") if font else None
    justify = child(effects, "justify") if effects else None
    justifications = {item for item in (justify or [])[1:] if isinstance(item, str)}
    return number(atom(size, 1), 1.27), number(atom(size, 2), 1.27), justifications


def text_units(value: str) -> float:
    total = 0.0
    for char in value:
        if char.isspace():
            total += 0.35
        elif unicodedata.east_asian_width(char) in {"W", "F", "A"}:
            total += 1.0
        else:
            total += 0.62
    return max(total, 0.62)


def rotated_box(box: Box, anchor: Point, angle: float) -> Box:
    radians = math.radians(angle % 360)
    cosine, sine = math.cos(radians), math.sin(radians)
    points = []
    for point in (
        Point(box.left, box.top),
        Point(box.right, box.top),
        Point(box.right, box.bottom),
        Point(box.left, box.bottom),
    ):
        dx, dy = point.x - anchor.x, point.y - anchor.y
        points.append(Point(anchor.x + dx * cosine - dy * sine, anchor.y + dx * sine + dy * cosine))
    return box_from_points(points)


def text_box(value: str, node: Sequence[SExpr], padding: float = 0.12) -> tuple[Box, Point]:
    anchor, angle = at_from(node)
    font_x, font_y, justify = effects_data(node)
    lines = value.splitlines() or [""]
    width = max(text_units(line) for line in lines) * font_x + padding * 2
    height = len(lines) * font_y * 1.15 + padding * 2
    if "left" in justify:
        left, right = anchor.x, anchor.x + width
    elif "right" in justify:
        left, right = anchor.x - width, anchor.x
    else:
        left, right = anchor.x - width / 2, anchor.x + width / 2
    if "top" in justify:
        top, bottom = anchor.y, anchor.y + height
    elif "bottom" in justify:
        top, bottom = anchor.y - height, anchor.y
    else:
        top, bottom = anchor.y - height / 2, anchor.y + height / 2
    return rotated_box(Box(left, top, right, bottom), anchor, angle), anchor


def graphic_points(node: Sequence[SExpr]) -> list[Point]:
    name = node_name(node)
    if name == "rectangle":
        return [point_from(child(node, "start")), point_from(child(node, "end"))]
    if name == "circle":
        center = point_from(child(node, "center"))
        radius = number(atom(child(node, "radius"), 1))
        return [Point(center.x - radius, center.y - radius), Point(center.x + radius, center.y + radius)]
    if name in {"polyline", "bezier", "arc"}:
        pts = child(node, "pts")
        if pts:
            return [point_from(item) for item in pts[1:] if isinstance(item, list) and node_name(item) == "xy"]
        return [point_from(item) for item in node[1:] if isinstance(item, list) and node_name(item) in {"start", "mid", "end"}]
    return []


def collect_graphic_points(node: Sequence[SExpr]) -> list[Point]:
    points: list[Point] = []
    for item in node[1:]:
        if not isinstance(item, list):
            continue
        if node_name(item) in {"rectangle", "circle", "polyline", "bezier", "arc"}:
            points.extend(graphic_points(item))
        elif node_name(item) == "symbol":
            points.extend(collect_graphic_points(item))
    return points


def transform_local(point: Point, origin: Point, angle: float, mirrors: set[str]) -> Point:
    x, y = point.x, point.y
    if "y" in mirrors:
        x = -x
    if "x" in mirrors:
        y = -y
    radians = math.radians(angle % 360)
    rotated_x = x * math.cos(radians) - y * math.sin(radians)
    rotated_y = x * math.sin(radians) + y * math.cos(radians)
    return Point(origin.x + rotated_x, origin.y - rotated_y)


def extract_symbols(root: Sequence[SExpr]) -> tuple[list[VisualItem], list[VisualItem]]:
    library_section = child(root, "lib_symbols")
    libraries = {
        atom(item, 1): item
        for item in (library_section or [])[1:]
        if isinstance(item, list) and node_name(item) == "symbol"
    }
    symbols: list[VisualItem] = []
    properties: list[VisualItem] = []
    for instance in children(root, "symbol"):
        lib_id = atom(child(instance, "lib_id"), 1)
        reference = "?"
        for prop in children(instance, "property"):
            if atom(prop, 1) == "Reference":
                reference = atom(prop, 2, "?")
                break
        origin, angle = at_from(instance)
        mirror = child(instance, "mirror")
        mirrors = {item for item in (mirror or [])[1:] if isinstance(item, str)}
        local_points = collect_graphic_points(libraries.get(lib_id, []))
        if local_points:
            body = box_from_points([transform_local(point, origin, angle, mirrors) for point in local_points])
        else:
            body = Box(origin.x - 1.27, origin.y - 1.27, origin.x + 1.27, origin.y + 1.27)
        symbols.append(VisualItem("symbol", reference, body, origin, reference))
        for prop in children(instance, "property"):
            if not visible(prop):
                continue
            prop_name, value = atom(prop, 1), atom(prop, 2)
            if not value:
                continue
            bbox, anchor = text_box(value, prop)
            properties.append(VisualItem("property", f"{reference}.{prop_name}", bbox, anchor, reference))
    return symbols, properties


def extract_symbol_records(root: Sequence[SExpr]) -> list[SymbolRecord]:
    library_section = child(root, "lib_symbols")
    libraries = {
        atom(item, 1): item
        for item in (library_section or [])[1:]
        if isinstance(item, list) and node_name(item) == "symbol"
    }
    pin_cache: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {}
    records: list[SymbolRecord] = []
    for instance in children(root, "symbol"):
        lib_id = atom(child(instance, "lib_id"), 1)
        properties = {atom(prop, 1): atom(prop, 2) for prop in children(instance, "property")}
        if lib_id not in pin_cache:
            definition = pin_definition(lib_id, recursive_nodes(libraries.get(lib_id, []), "pin"))
            pin_cache[lib_id] = (
                definition.pin_numbers,
                definition.pin_names,
                definition.pin_types,
                definition.pin_conflicts,
            )
        pin_numbers, pin_names, pin_types, pin_conflicts = pin_cache[lib_id]
        records.append(
            SymbolRecord(
                reference=properties.get("Reference", "?"),
                value=properties.get("Value", ""),
                lib_id=lib_id,
                footprint=properties.get("Footprint", ""),
                datasheet=properties.get("Datasheet", ""),
                description=properties.get("Description", ""),
                pin_count=len(pin_numbers),
                pin_numbers=pin_numbers,
                pin_names=pin_names,
                pin_types=pin_types,
                pin_conflicts=pin_conflicts,
            )
        )
    return records


def extract_text_items(root: Sequence[SExpr]) -> list[VisualItem]:
    items: list[VisualItem] = []
    for kind in ("text", "text_box", "label", "global_label", "hierarchical_label"):
        for node in children(root, kind):
            if not visible(node):
                continue
            value = atom(node, 1)
            if not value:
                continue
            bbox, anchor = text_box(value, node)
            identity = f"{kind}:{value}@{anchor.x:.2f},{anchor.y:.2f}"
            items.append(VisualItem(kind, identity, bbox, anchor))
    return items


def extract_wires(root: Sequence[SExpr]) -> list[Wire]:
    wires: list[Wire] = []
    for index, node in enumerate(children(root, "wire"), start=1):
        pts = child(node, "pts")
        points = [point_from(item) for item in (pts or [])[1:] if isinstance(item, list) and node_name(item) == "xy"]
        for segment_index in range(len(points) - 1):
            identity = f"wire:{uuid_from(node, str(index))}:{segment_index + 1}"
            wires.append(Wire(points[segment_index], points[segment_index + 1], identity))
    return wires


def normalize_segment(first: Point, second: Point) -> tuple[Point, Point]:
    return (first, second) if (first.x, first.y) <= (second.x, second.y) else (second, first)


def extract_frames(root: Sequence[SExpr], minimum_area: float) -> list[Frame]:
    frames: list[Frame] = []
    horizontal: list[tuple[Point, Point, str]] = []
    vertical: list[tuple[Point, Point, str]] = []
    for index, node in enumerate(children(root, "rectangle"), start=1):
        points = graphic_points(node)
        if len(points) >= 2:
            bbox = box_from_points(points)
            if bbox.area >= minimum_area:
                frames.append(Frame(f"rectangle:{uuid_from(node, str(index))}", bbox))
    for index, node in enumerate(children(root, "polyline"), start=1):
        points = graphic_points(node)
        closed = (
            len(points) >= 4
            and abs(points[0].x - points[-1].x) < EPSILON
            and abs(points[0].y - points[-1].y) < EPSILON
        )
        if closed:
            bbox = box_from_points(points)
            if bbox.area >= minimum_area:
                frames.append(Frame(f"polyline:{uuid_from(node, str(index))}", bbox))
            continue
        for first, second in zip(points, points[1:]):
            first, second = normalize_segment(first, second)
            identity = f"polyline:{uuid_from(node, str(index))}"
            if abs(first.y - second.y) < EPSILON:
                horizontal.append((first, second, identity))
            elif abs(first.x - second.x) < EPSILON:
                vertical.append((first, second, identity))
    for top_start, top_end, top_id in horizontal:
        for bottom_start, bottom_end, bottom_id in horizontal:
            if bottom_start.y <= top_start.y + EPSILON:
                continue
            if abs(top_start.x - bottom_start.x) > EPSILON or abs(top_end.x - bottom_end.x) > EPSILON:
                continue
            left_exists = any(
                abs(start.x - top_start.x) < EPSILON
                and abs(start.y - top_start.y) < EPSILON
                and abs(end.y - bottom_start.y) < EPSILON
                for start, end, _ in vertical
            )
            right_exists = any(
                abs(start.x - top_end.x) < EPSILON
                and abs(start.y - top_end.y) < EPSILON
                and abs(end.y - bottom_end.y) < EPSILON
                for start, end, _ in vertical
            )
            bbox = Box(top_start.x, top_start.y, top_end.x, bottom_start.y)
            if left_exists and right_exists and bbox.area >= minimum_area:
                frames.append(Frame(f"frame:{top_id}+{bottom_id}", bbox))
    unique: dict[tuple[float, float, float, float], Frame] = {}
    for frame in frames:
        key = tuple(round(value, 3) for value in asdict(frame.box).values())
        unique[key] = frame
    return sorted(unique.values(), key=lambda item: item.box.area)


def page_dimensions(root: Sequence[SExpr]) -> tuple[float, float]:
    paper = child(root, "paper")
    name = atom(paper, 1, "A4")
    if name == "User":
        width, height = number(atom(paper, 2), 297.0), number(atom(paper, 3), 210.0)
    else:
        width, height = PAGE_SIZES_MM.get(name, PAGE_SIZES_MM["A4"])
    if any(isinstance(item, str) and item == "portrait" for item in (paper or [])[2:]):
        width, height = min(width, height), max(width, height)
    else:
        width, height = max(width, height), min(width, height)
    return width, height


def page_box(root: Sequence[SExpr], margin: float) -> Box:
    width, height = page_dimensions(root)
    return Box(margin, margin, width - margin, height - margin)


def title_block_box(root: Sequence[SExpr], margin: float, width: float, height: float) -> Box:
    page_width, page_height = page_dimensions(root)
    return Box(page_width - margin - width, page_height - margin - height, page_width - margin, page_height - margin)


def frame_sides(frame: Frame) -> list[Wire]:
    box = frame.box
    points = [Point(box.left, box.top), Point(box.right, box.top), Point(box.right, box.bottom), Point(box.left, box.bottom)]
    return [Wire(points[index], points[(index + 1) % 4], f"{frame.identity}:side{index + 1}") for index in range(4)]


def estimate_density(frame: Frame, items: Sequence[VisualItem], wires: Sequence[Wire], cell_size: float) -> tuple[float, int]:
    columns = max(1, math.ceil(frame.box.width / cell_size))
    rows = max(1, math.ceil(frame.box.height / cell_size))
    occupied: set[tuple[int, int]] = set()

    def mark_box(box: Box) -> None:
        clipped = Box(
            max(frame.box.left, box.left),
            max(frame.box.top, box.top),
            min(frame.box.right, box.right),
            min(frame.box.bottom, box.bottom),
        )
        if clipped.width <= 0 or clipped.height <= 0:
            return
        first_col = max(0, int((clipped.left - frame.box.left) / cell_size))
        last_col = min(columns - 1, int((clipped.right - frame.box.left) / cell_size))
        first_row = max(0, int((clipped.top - frame.box.top) / cell_size))
        last_row = min(rows - 1, int((clipped.bottom - frame.box.top) / cell_size))
        for column in range(first_col, last_col + 1):
            for row in range(first_row, last_row + 1):
                occupied.add((column, row))

    contained_items = [item for item in items if frame.box.contains_point(item.box.center)]
    for item in contained_items:
        mark_box(item.box)
    for wire in wires:
        if frame.box.contains_point(wire.start) or frame.box.contains_point(wire.end):
            mark_box(wire.box.expanded(0.25))
    return len(occupied) / (columns * rows), len(contained_items)


def run_visual_audit(
    root: Sequence[SExpr],
    text_clearance: float,
    symbol_clearance: float,
    module_clearance: float,
    page_margin: float,
    minimum_frame_area: float,
    density_cell: float,
    max_module_density: float,
    max_zone_density: float,
    max_items_per_1000: float,
    title_block_width: float,
    title_block_height: float,
) -> tuple[list[Issue], dict[str, object]]:
    symbols, properties = extract_symbols(root)
    texts = properties + extract_text_items(root)
    wires = extract_wires(root)
    frames = extract_frames(root, minimum_frame_area)
    issues: list[Issue] = []
    unique_wires: list[Wire] = []
    wire_groups: dict[tuple[float, float, float, float], list[Wire]] = {}
    for wire in wires:
        first, second = normalize_segment(wire.start, wire.end)
        key = (round(first.x, 6), round(first.y, 6), round(second.x, 6), round(second.y, 6))
        wire_groups.setdefault(key, []).append(wire)
    for group in wire_groups.values():
        unique_wires.append(group[0])
        if len(group) > 1:
            issues.append(
                Issue(
                    "duplicate-wire",
                    "warning",
                    f"The same wire segment is stored {len(group)} times",
                    tuple(wire.identity for wire in group),
                    (group[0].box.center.x, group[0].box.center.y),
                )
            )

    for index, first in enumerate(symbols):
        for second in symbols[index + 1 :]:
            if boxes_overlap(first.box, second.box, symbol_clearance):
                actual_overlap = boxes_overlap(first.box, second.box)
                issues.append(
                    Issue(
                        "symbol-overlap" if actual_overlap else "symbol-clearance",
                        "error" if actual_overlap else "warning",
                        "Symbol bodies overlap"
                        if actual_overlap
                        else f"Symbol body clearance is less than {symbol_clearance:g} mm",
                        (first.identity, second.identity),
                        overlap_center(first.box, second.box),
                    )
                )

    for index, first in enumerate(texts):
        for second in texts[index + 1 :]:
            if boxes_overlap(first.box, second.box, text_clearance):
                issues.append(
                    Issue(
                        "text-collision",
                        "warning",
                        f"Visible text overlaps or is closer than {text_clearance:g} mm",
                        (first.identity, second.identity),
                        overlap_center(first.box, second.box),
                    )
                )

    for text in texts:
        for symbol in symbols:
            if text.anchor and text.kind in {"label", "global_label", "hierarchical_label"}:
                anchor = text.anchor
                if symbol.box.contains_point(anchor):
                    edge_distance = min(
                        abs(anchor.x - symbol.box.left),
                        abs(anchor.x - symbol.box.right),
                        abs(anchor.y - symbol.box.top),
                        abs(anchor.y - symbol.box.bottom),
                    )
                    if edge_distance <= symbol_clearance:
                        continue
            if boxes_overlap(text.box, symbol.box, text_clearance):
                issues.append(
                    Issue(
                        "text-symbol-collision",
                        "warning",
                        "Visible text intersects a symbol body",
                        (text.identity, symbol.identity),
                        overlap_center(text.box, symbol.box),
                    )
                )

    for wire in unique_wires:
        for symbol in symbols:
            if segment_intersects_box(wire, symbol.box, inset=0.08):
                issues.append(
                    Issue(
                        "wire-through-symbol",
                        "error",
                        "Wire passes through a symbol body",
                        (wire.identity, symbol.identity),
                        segment_box_intersection_location(wire, symbol.box),
                    )
                )
        for text in texts:
            if text.anchor and (
                math.hypot(wire.start.x - text.anchor.x, wire.start.y - text.anchor.y) < EPSILON
                or math.hypot(wire.end.x - text.anchor.x, wire.end.y - text.anchor.y) < EPSILON
            ) and text.kind in {"label", "global_label", "hierarchical_label"}:
                continue
            if segment_intersects_box(wire, text.box.expanded(text_clearance / 2)):
                issues.append(
                    Issue(
                        "wire-through-text",
                        "warning",
                        "Wire intersects visible text",
                        (wire.identity, text.identity),
                        segment_box_intersection_location(wire, text.box),
                    )
                )

    for wire in unique_wires:
        for frame in frames:
            if any(segments_intersect(wire, side) for side in frame_sides(frame)):
                issues.append(
                    Issue(
                        "wire-crosses-module-frame",
                        "error",
                        "Wire touches or crosses a module frame",
                        (wire.identity, frame.identity),
                        None,
                    )
                )

    for frame in frames:
        for item in symbols + texts:
            crossing_side = next((side for side in frame_sides(frame) if segment_intersects_box(side, item.box)), None)
            if crossing_side:
                issues.append(
                    Issue(
                        "module-frame-through-content",
                        "error",
                        "Module frame passes through a symbol or visible text",
                        (frame.identity, item.identity),
                        segment_box_intersection_location(crossing_side, item.box),
                    )
                )

    content_items = symbols + texts
    safe_page = page_box(root, page_margin)
    reserved_title_block = title_block_box(root, page_margin, title_block_width, title_block_height)
    for item in content_items:
        if not safe_page.contains_box(item.box):
            issues.append(
                Issue(
                    "page-boundary-clearance",
                    "warning",
                    f"Content is outside the {page_margin:g} mm page safe margin",
                    (item.identity,),
                    (item.box.center.x, item.box.center.y),
                )
            )
        containing_frames = [frame for frame in frames if frame.box.contains_point(item.box.center)]
        if containing_frames:
            frame = min(containing_frames, key=lambda candidate: candidate.box.area)
            if not frame.box.contains_box(item.box, module_clearance):
                issues.append(
                    Issue(
                        "module-boundary-clearance",
                        "warning",
                        f"Content is closer than {module_clearance:g} mm to its module frame",
                        (item.identity, frame.identity),
                        (item.box.center.x, item.box.center.y),
                    )
                )
        if boxes_overlap(item.box, reserved_title_block):
            issues.append(
                Issue(
                    "title-block-intrusion",
                    "error",
                    "Content intrudes into the reserved title-block area",
                    (item.identity, "title-block"),
                    overlap_center(item.box, reserved_title_block),
                )
            )

    density_metrics: list[dict[str, object]] = []
    for frame in frames:
        if not safe_page.contains_box(frame.box):
            issues.append(
                Issue(
                    "module-frame-page-boundary",
                    "warning",
                    f"Module frame is outside the {page_margin:g} mm page safe margin",
                    (frame.identity,),
                    (frame.box.center.x, frame.box.center.y),
                )
            )
        if boxes_overlap(frame.box, reserved_title_block):
            issues.append(
                Issue(
                    "module-frame-title-block-intrusion",
                    "error",
                    "Module frame intrudes into the reserved title-block area",
                    (frame.identity, "title-block"),
                    overlap_center(frame.box, reserved_title_block),
                )
            )
        density, item_count = estimate_density(frame, content_items, unique_wires, density_cell)
        items_per_1000 = item_count * 1000 / frame.box.area
        density_metrics.append(
            {
                "frame": frame.identity,
                "box": asdict(frame.box),
                "occupied_ratio": round(density, 4),
                "item_count": item_count,
                "items_per_1000mm2": round(items_per_1000, 2),
            }
        )
        if density > max_module_density:
            issues.append(
                Issue(
                    "module-density",
                    "warning",
                    f"Occupied ratio {density:.1%} exceeds {max_module_density:.1%}",
                    (frame.identity,),
                    (frame.box.center.x, frame.box.center.y),
                )
            )
        if items_per_1000 > max_items_per_1000:
            issues.append(
                Issue(
                    "module-item-density",
                    "warning",
                    f"Item density {items_per_1000:.1f}/1000mm2 exceeds {max_items_per_1000:.1f}",
                    (frame.identity,),
                    (frame.box.center.x, frame.box.center.y),
                )
            )

    zone_width, zone_height = safe_page.width / 3, safe_page.height / 2
    for row in range(2):
        for column in range(3):
            zone = Frame(
                f"page-zone-{row + 1}-{column + 1}",
                Box(
                    safe_page.left + column * zone_width,
                    safe_page.top + row * zone_height,
                    safe_page.left + (column + 1) * zone_width,
                    safe_page.top + (row + 1) * zone_height,
                ),
            )
            density, item_count = estimate_density(zone, content_items, unique_wires, density_cell)
            density_metrics.append(
                {
                    "frame": zone.identity,
                    "kind": "page-zone",
                    "box": asdict(zone.box),
                    "occupied_ratio": round(density, 4),
                    "item_count": item_count,
                    "items_per_1000mm2": round(item_count * 1000 / zone.box.area, 2),
                }
            )
            if density > max_zone_density:
                issues.append(
                    Issue(
                        "page-zone-density",
                        "warning",
                        f"Page-zone occupied ratio {density:.1%} exceeds {max_zone_density:.1%}",
                        (zone.identity,),
                        (zone.box.center.x, zone.box.center.y),
                    )
                )
    summary = {
        "symbols": len(symbols),
        "visible_text_items": len(texts),
        "wires": len(wires),
        "unique_wires": len(unique_wires),
        "module_frames": len(frames),
        "issues": len(issues),
        "errors": sum(issue.severity == "error" for issue in issues),
        "warnings": sum(issue.severity == "warning" for issue in issues),
        "density": density_metrics,
    }
    return issues, summary


def find_balanced_block(text: str, start: int) -> tuple[int, int]:
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return start, index + 1
    raise ValueError("Unbalanced S-expression")


def parse_netlist(text: str) -> tuple[dict[str, set[tuple[str, str]]], list[str]]:
    nets: dict[str, set[tuple[str, str]]] = {}
    nets_start = text.find("\n\t(nets")
    if nets_start < 0:
        raise ValueError("Netlist has no nets section")
    section_start, section_end = find_balanced_block(text, nets_start + 2)
    section = text[section_start:section_end]
    cursor = 0
    while True:
        start = section.find("\n\t\t(net", cursor)
        if start < 0:
            break
        start += 3
        block_start, block_end = find_balanced_block(section, start)
        block = section[block_start:block_end]
        name_match = re.search(r'\(name "([^"]+)"\)', block)
        if name_match:
            name = name_match.group(1).lstrip("/")
            nodes = set(re.findall(r'\(node\s+\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)', block, re.MULTILINE))
            nets[name] = nodes
        cursor = block_end
    components_start = text.find("\n\t(components")
    libparts_start = text.find("\n\t(libparts")
    component_text = text[components_start:libparts_start] if components_start >= 0 and libparts_start > 0 else ""
    refs = re.findall(r'\(comp\s+\(ref "([^"]+)"\)', component_text, re.MULTILINE)
    return nets, refs


def parse_expectation(raw: str) -> tuple[str, set[tuple[str, str]]]:
    if "=" not in raw:
        raise ValueError(f"Invalid --expect-net value: {raw}")
    name, raw_nodes = raw.split("=", 1)
    nodes: set[tuple[str, str]] = set()
    for raw_node in filter(None, (item.strip() for item in raw_nodes.split(","))):
        if ":" not in raw_node:
            raise ValueError(f"Invalid expected node: {raw_node}")
        ref, pin = raw_node.split(":", 1)
        nodes.add((ref.strip(), pin.strip()))
    return name.strip().lstrip("/"), nodes


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def main() -> int:
    args = parse_args()
    try:
        checks = resolve_checks(args)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    schematic = args.schematic.resolve()
    if not schematic.is_file():
        print(f"ERROR: schematic not found: {schematic}")
        return 2
    try:
        text = schematic.read_text(encoding="utf-8")
        root = parse_sexpr(text)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: could not parse schematic: {exc}")
        return 2

    output_dir = (args.output_dir or schematic.with_name(f"{schematic.stem}-audit")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_kicad_cli = locate_kicad_cli(args.kicad_cli)
    print(f"Schematic: {schematic}")
    print(f"Checks: {', '.join(sorted(checks)) or 'none'}")

    standard_symbol_dir = None
    standard_index = None
    project_libraries: dict[str, object] = {}
    symbol_results: list[dict[str, object]] = []
    symbol_findings = []
    symbol_summary = {
        "instances": 0,
        "standard": 0,
        "project_custom": 0,
        "embedded_custom": 0,
        "approved_custom": 0,
        "approved_exceptions": 0,
        "errors": 0,
        "warnings": 0,
        "blocking": 0,
    }
    default_policy_path = Path(__file__).resolve().parent.parent / "references" / "standard-symbol-policy.json"
    policy_path = (args.symbol_policy or default_policy_path).resolve()
    default_manifest_path = schematic.with_name(f"{schematic.stem}.symbol-manifest.json")
    manifest_path = (args.symbol_manifest or default_manifest_path).resolve()
    if "symbol" in checks:
        try:
            if args.symbol_policy and not policy_path.is_file():
                raise ValueError(f"symbol policy not found: {policy_path}")
            if args.symbol_manifest and not manifest_path.is_file():
                raise ValueError(f"symbol manifest not found: {manifest_path}")
            policy = load_json(policy_path, {})
            manifest = load_json(manifest_path if manifest_path.is_file() else None, {"version": 1})
            standard_symbol_dir = locate_standard_symbol_dir(args.kicad_symbol_dir, resolved_kicad_cli)
            standard_index = (
                build_standard_index(
                    standard_symbol_dir,
                    args.symbol_index_cache,
                    not args.no_symbol_index_cache,
                )
                if standard_symbol_dir
                else None
            )
            project_libraries = parse_project_libraries(schematic.parent)
            symbol_results, symbol_findings, symbol_summary = evaluate_symbol_policy(
                extract_symbol_records(root), standard_index, project_libraries, policy, manifest
            )
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR: symbol policy audit failed: {exc}")
            return 2

        print(
            "Symbol provenance: "
            f"{symbol_summary['standard']} standard, {symbol_summary['project_custom']} project custom, "
            f"{symbol_summary['embedded_custom']} embedded custom"
        )
        print(
            f"Symbol findings: {symbol_summary['errors']} errors, {symbol_summary['warnings']} warnings, "
            f"{symbol_summary['blocking']} blocking"
        )
        if standard_index and standard_index.cache_path:
            print(f"Symbol index cache: {'hit' if standard_index.cache_hit else 'rebuilt'} ({standard_index.cache_path})")
        for finding in symbol_findings[: args.max_reported_issues]:
            candidates = f"; candidates: {', '.join(finding.candidates)}" if finding.candidates else ""
            print(
                f"SYMBOL {finding.severity.upper()} [{finding.rule}]: "
                f"{finding.reference} {finding.lib_id}: {finding.message}{candidates}"
            )
        if len(symbol_findings) > args.max_reported_issues:
            print(f"SYMBOL: {len(symbol_findings) - args.max_reported_issues} additional findings are in the JSON report")

    wires = extract_wires(root) if checks & {"wires", "visual"} else []
    diagonals = [wire for wire in wires if not wire.orthogonal]
    zero_length = [wire for wire in wires if wire.zero_length]
    over_length = [wire for wire in wires if args.max_wire_mm is not None and wire.length > args.max_wire_mm]
    if "wires" in checks:
        print(f"Wires: {len(wires)}")
        print(f"Labels: {len(children(root, 'label'))}")
        print(f"Junctions: {len(children(root, 'junction'))}")
        print(f"Diagonal wires: {len(diagonals)}")
        print(f"Zero-length wires: {len(zero_length)}")
        if args.max_wire_mm is not None:
            print(f"Wires over {args.max_wire_mm:g} mm: {len(over_length)}")

    visual_issues: list[Issue] = []
    visual_summary: dict[str, object] = {}
    if "visual" in checks:
        visual_issues, visual_summary = run_visual_audit(
            root,
            args.text_clearance_mm,
            args.symbol_clearance_mm,
            args.module_clearance_mm,
            args.page_margin_mm,
            args.min_frame_area_mm2,
            args.density_cell_mm,
            args.max_module_density,
            args.max_zone_density,
            args.max_items_per_1000mm2,
            args.title_block_width_mm,
            args.title_block_height_mm,
        )
        print(
            "Visual geometry: "
            f"{visual_summary['symbols']} symbols, {visual_summary['visible_text_items']} visible texts, "
            f"{visual_summary['module_frames']} module frames"
        )
        print(f"Visual issues: {visual_summary['errors']} errors, {visual_summary['warnings']} warnings")
        for issue in visual_issues[: args.max_reported_issues]:
            location = f" at ({issue.location[0]:.2f}, {issue.location[1]:.2f})" if issue.location else ""
            print(f"VISUAL {issue.severity.upper()} [{issue.rule}]{location}: {issue.message}: {', '.join(issue.objects)}")
        if len(visual_issues) > args.max_reported_issues:
            print(f"VISUAL: {len(visual_issues) - args.max_reported_issues} additional issues are in the JSON report")

    failures: list[str] = []
    if "wires" in checks and diagonals:
        failures.append("diagonal wires found")
    if "wires" in checks and zero_length:
        failures.append("zero-length wires found")
    if "wires" in checks and over_length:
        failures.append("wire segment length limit exceeded")
    failures.extend(
        visual_gate_failures(
            visual_issues,
            args.fail_on_visual or args.fail_on_visual_warnings,
            args.fail_on_visual_warnings,
        )
    )
    if "symbol" in checks and args.strict_symbol_policy and symbol_summary["blocking"]:
        failures.append("symbol provenance policy violations or unresolved custom symbols found")

    if "visual" in checks:
        visual_report = (args.visual_report or output_dir / f"{schematic.stem}-visual.json").resolve()
        report_payload = {
            "schematic": str(schematic),
            "thresholds": {
                "text_clearance_mm": args.text_clearance_mm,
                "symbol_clearance_mm": args.symbol_clearance_mm,
                "module_clearance_mm": args.module_clearance_mm,
                "page_margin_mm": args.page_margin_mm,
                "max_module_density": args.max_module_density,
                "max_zone_density": args.max_zone_density,
                "max_items_per_1000mm2": args.max_items_per_1000mm2,
                "title_block_width_mm": args.title_block_width_mm,
                "title_block_height_mm": args.title_block_height_mm,
            },
            "summary": visual_summary,
            "issues": [asdict(issue) for issue in visual_issues],
        }
        visual_report.parent.mkdir(parents=True, exist_ok=True)
        visual_report.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Visual report: {visual_report}")

    if "symbol" in checks:
        symbol_report = (args.symbol_report or output_dir / f"{schematic.stem}-symbols.json").resolve()
        symbol_payload = {
            "schematic": str(schematic),
            "standard_symbol_dir": str(standard_symbol_dir) if standard_symbol_dir else None,
            "standard_index_cache": (
                {"path": standard_index.cache_path, "hit": standard_index.cache_hit} if standard_index else None
            ),
            "policy": str(policy_path),
            "manifest": str(manifest_path) if manifest_path.is_file() else None,
            "project_libraries": {
                name: {
                    "uri": item.uri,
                    "path": item.path,
                    "exists": item.exists,
                    "symbols": list(item.symbols),
                }
                for name, item in project_libraries.items()
            },
            "summary": symbol_summary,
            "findings": [asdict(item) for item in symbol_findings],
            "instances": symbol_results,
        }
        symbol_report.parent.mkdir(parents=True, exist_ok=True)
        symbol_report.write_text(json.dumps(symbol_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Symbol report: {symbol_report}")

    if "cli" in checks and (not resolved_kicad_cli or not resolved_kicad_cli.is_file()):
        message = "kicad-cli not found; skipped ERC, netlist, and SVG export"
        if args.require_cli:
            failures.append(message)
        else:
            print(f"WARNING: {message}")
    elif "cli" in checks:
        kicad_cli = resolved_kicad_cli
        erc_path = output_dir / f"{schematic.stem}-erc.rpt"
        netlist_path = output_dir / f"{schematic.stem}.net"
        svg_dir = output_dir / "svg"
        svg_dir.mkdir(exist_ok=True)
        commands = [
            ("ERC", [str(kicad_cli), "sch", "erc", "--output", str(erc_path), str(schematic)]),
            ("netlist", [str(kicad_cli), "sch", "export", "netlist", "--output", str(netlist_path), str(schematic)]),
            ("SVG", [str(kicad_cli), "sch", "export", "svg", "--output", str(svg_dir), str(schematic)]),
        ]
        for label, command in commands:
            result = run(command, schematic.parent)
            if result.returncode != 0:
                failures.append(f"{label} command failed with exit code {result.returncode}")
                if result.stdout.strip():
                    print(result.stdout.strip())
                if result.stderr.strip():
                    print(result.stderr.strip())
        if erc_path.exists():
            erc_text = erc_path.read_text(encoding="utf-8", errors="replace")
            summary = re.search(r"ERC messages:\s*(\d+)\s+Errors\s+(\d+)\s+Warnings", erc_text)
            if summary:
                errors, warnings = (int(value) for value in summary.groups())
                print(f"ERC: {errors} errors, {warnings} warnings")
                if errors:
                    failures.append("ERC errors found")
                if warnings and not args.allow_erc_warnings:
                    failures.append("ERC warnings found")
            else:
                failures.append("could not parse ERC summary")
        if netlist_path.exists():
            net_text = netlist_path.read_text(encoding="utf-8", errors="replace")
            nets, refs = parse_netlist(net_text)
            duplicate_refs = sorted(ref for ref in set(refs) if refs.count(ref) > 1)
            print(f"Components: {len(refs)}")
            print(f"Duplicate references: {', '.join(duplicate_refs) if duplicate_refs else 'none'}")
            if duplicate_refs:
                failures.append("duplicate component references found")
            for raw_expectation in args.expect_net:
                try:
                    name, expected_nodes = parse_expectation(raw_expectation)
                except ValueError as exc:
                    failures.append(str(exc))
                    continue
                actual_nodes = nets.get(name)
                if actual_nodes is None:
                    failures.append(f"expected net not found: {name}")
                    continue
                missing = sorted(expected_nodes - actual_nodes)
                if missing:
                    failures.append(f"net {name} missing nodes: {missing}")
                else:
                    print(f"Net {name}: expected nodes present")
        if args.render_png:
            svg_path = svg_dir / f"{schematic.stem}.svg"
            png_path = output_dir / f"{schematic.stem}.png"
            if svg_path.exists():
                result = run([sys.executable, "-m", "cairosvg", str(svg_path), "-o", str(png_path)], schematic.parent)
                if result.returncode != 0:
                    failures.append("PNG render failed; install cairosvg or omit --render-png")
                else:
                    print(f"PNG: {png_path}")
        print(f"Audit outputs: {output_dir}")

    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    if visual_issues and not args.fail_on_visual and not args.fail_on_visual_warnings:
        print("ADVISORY: visual findings were reported but no visual failure gate was enabled")
    if "symbol" in checks and symbol_summary["blocking"] and not args.strict_symbol_policy:
        print("ADVISORY: blocking symbol findings were reported but strict symbol policy was not enabled")
    print("PASS: all enabled failure gates passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
