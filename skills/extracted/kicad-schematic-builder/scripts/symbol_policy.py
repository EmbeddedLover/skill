#!/usr/bin/env python3
"""KiCad standard-symbol provenance and custom-symbol policy checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from difflib import SequenceMatcher
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Iterable
from urllib.parse import unquote, urlparse

from kicad_sexpr import SExpr, atom, child, children, parse as parse_sexpr, recursive_nodes, tokenize


STANDARD_INDEX_CACHE_VERSION = 2


@dataclass(frozen=True)
class SymbolRecord:
    reference: str
    value: str
    lib_id: str
    footprint: str
    datasheet: str
    description: str
    pin_count: int
    pin_numbers: tuple[str, ...]
    pin_names: tuple[str, ...]
    pin_types: tuple[str, ...]
    pin_conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class SymbolFinding:
    rule: str
    severity: str
    blocking: bool
    reference: str
    lib_id: str
    message: str
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectLibrary:
    name: str
    uri: str
    path: str | None
    exists: bool
    symbols: tuple[str, ...] = ()
    definitions: tuple["LibrarySymbol", ...] = ()

    def definition(self, name: str) -> "LibrarySymbol | None":
        return next((item for item in self.definitions if item.name == name), None)


@dataclass(frozen=True)
class LibrarySymbol:
    name: str
    pin_numbers: tuple[str, ...]
    pin_names: tuple[str, ...]
    pin_types: tuple[str, ...]
    pin_conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class StandardIndex:
    root: str
    symbols: frozenset[str]
    names: tuple[tuple[str, str], ...]
    libraries: frozenset[str]
    cache_path: str | None = None
    cache_hit: bool = False


def normalize_model(value: str) -> str:
    return "".join(char.upper() for char in value if char.isalnum())


def reference_prefix(reference: str) -> str:
    match = re.match(r"#?([A-Za-z]+)", reference)
    return match.group(1).upper() if match else ""


def split_lib_id(lib_id: str) -> tuple[str, str]:
    return tuple(lib_id.split(":", 1)) if ":" in lib_id else ("", lib_id)


def top_level_symbol_names(text: str) -> list[str]:
    names: list[str] = []
    depth = 0
    tokens = iter(tokenize(text))
    for token in tokens:
        if token == "(":
            depth += 1
            head = next(tokens, "")
            if depth == 2 and head == "symbol":
                name = next(tokens, "")
                if name and name not in {"(", ")"}:
                    names.append(name)
        elif token == ")":
            depth -= 1
    return names


def locate_standard_symbol_dir(explicit: Path | None, kicad_cli: Path | None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit)
    for variable in ("KICAD11_SYMBOL_DIR", "KICAD10_SYMBOL_DIR", "KICAD9_SYMBOL_DIR", "KICAD_SYMBOL_DIR"):
        value = os.environ.get(variable)
        if value:
            candidates.append(Path(value))
    if kicad_cli:
        resolved = kicad_cli.resolve()
        candidates.extend(
            [
                resolved.parent.parent / "share" / "kicad" / "symbols",
                resolved.parent.parent / "share" / "kicad" / "10.0" / "symbols",
            ]
        )
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    candidates.extend(
        [
            program_files / "KiCad" / "11.0" / "share" / "kicad" / "symbols",
            program_files / "KiCad" / "10.0" / "share" / "kicad" / "symbols",
            program_files / "KiCad" / "9.0" / "share" / "kicad" / "symbols",
            Path(r"D:\softwave\share\kicad\symbols"),
            Path("/usr/share/kicad/symbols"),
            Path("/usr/local/share/kicad/symbols"),
            Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"),
        ]
    )
    for candidate in candidates:
        if candidate.is_dir() and any(candidate.glob("*.kicad_sym")):
            return candidate.resolve()
    return None


def standard_index_fingerprint(root: Path) -> dict[str, int | str]:
    files = sorted(root.glob("*.kicad_sym"))
    stats = [path.stat() for path in files]
    digest = hashlib.sha256()
    for path, stat in zip(files, stats):
        digest.update(f"{path.name}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode("utf-8"))
    return {
        "file_count": len(files),
        "total_size": sum(item.st_size for item in stats),
        "latest_mtime_ns": max((item.st_mtime_ns for item in stats), default=0),
        "metadata_sha256": digest.hexdigest(),
    }


def default_standard_index_cache(root: Path) -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache")) / "Codex" / "kicad-symbol-index"
    key = hashlib.sha256(str(root.resolve()).lower().encode("utf-8")).hexdigest()[:16]
    return base / f"{key}.json"


def build_standard_index(root: Path, cache_path: Path | None = None, use_cache: bool = True) -> StandardIndex:
    root = root.resolve()
    fingerprint = standard_index_fingerprint(root)
    resolved_cache = (cache_path or default_standard_index_cache(root)).resolve()
    if use_cache and resolved_cache.is_file():
        try:
            payload = json.loads(resolved_cache.read_text(encoding="utf-8"))
            if (
                payload.get("version") == STANDARD_INDEX_CACHE_VERSION
                and payload.get("root") == str(root)
                and payload.get("fingerprint") == fingerprint
            ):
                names = tuple((str(item[0]), str(item[1])) for item in payload.get("names", []))
                return StandardIndex(
                    str(root),
                    frozenset(str(item) for item in payload.get("symbols", [])),
                    names,
                    frozenset(str(item) for item in payload.get("libraries", [])),
                    str(resolved_cache),
                    True,
                )
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError, TypeError):
            pass

    symbols: set[str] = set()
    names: list[tuple[str, str]] = []
    libraries: set[str] = set()
    for library_path in sorted(root.glob("*.kicad_sym")):
        library = library_path.stem
        libraries.add(library)
        text = library_path.read_text(encoding="utf-8", errors="replace")
        for name in top_level_symbol_names(text):
            symbols.add(f"{library}:{name}")
            names.append((f"{library}:{name}", name))
    index = StandardIndex(
        str(root),
        frozenset(symbols),
        tuple(names),
        frozenset(libraries),
        str(resolved_cache) if use_cache else None,
        False,
    )
    if use_cache:
        try:
            resolved_cache.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": STANDARD_INDEX_CACHE_VERSION,
                "root": str(root),
                "fingerprint": fingerprint,
                "symbols": sorted(symbols),
                "names": names,
                "libraries": sorted(libraries),
            }
            resolved_cache.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except (OSError, UnicodeError):
            pass
    return index


def pin_definition(name: str, pin_nodes: Iterable[list[SExpr]]) -> LibrarySymbol:
    ordered: dict[str, tuple[str, str]] = {}
    conflicts: set[str] = set()
    for pin in pin_nodes:
        number_value = atom(child(pin, "number"), 1)
        if not number_value:
            continue
        entry = (atom(child(pin, "name"), 1), atom(pin, 1, "passive"))
        previous = ordered.get(number_value)
        if previous is None:
            ordered[number_value] = entry
        elif previous != entry:
            conflicts.add(number_value)
    return LibrarySymbol(
        name,
        tuple(ordered),
        tuple(item[0] for item in ordered.values()),
        tuple(item[1] for item in ordered.values()),
        tuple(sorted(conflicts)),
    )


def parse_symbol_definitions(path: Path) -> tuple[LibrarySymbol, ...]:
    root = parse_sexpr(path.read_text(encoding="utf-8", errors="replace"))
    nodes = {atom(item, 1): item for item in children(root, "symbol")}
    resolved: dict[str, LibrarySymbol] = {}

    def resolve(name: str, stack: tuple[str, ...] = ()) -> LibrarySymbol:
        if name in resolved:
            return resolved[name]
        if name in stack:
            raise ValueError(f"Circular symbol inheritance in {path}: {' -> '.join((*stack, name))}")
        node = nodes[name]
        pins: list[list[SExpr]] = []
        base_name = atom(child(node, "extends"), 1)
        if base_name and base_name in nodes:
            base = resolve(base_name, (*stack, name))
            for number_value, pin_name, pin_type in zip(base.pin_numbers, base.pin_names, base.pin_types):
                pins.append(["pin", pin_type, ["name", pin_name], ["number", number_value]])
        pins.extend(recursive_nodes(node, "pin"))
        result = pin_definition(name, pins)
        resolved[name] = result
        return result

    return tuple(resolve(name) for name in nodes)


def expand_kicad_uri(uri: str, schematic_dir: Path) -> str:
    variables = {**os.environ, "KIPRJMOD": str(schematic_dir)}
    return re.sub(r"\$\{([^}]+)\}", lambda match: variables.get(match.group(1), match.group(0)), uri)


def parse_project_libraries(schematic_dir: Path) -> dict[str, ProjectLibrary]:
    table_path = schematic_dir / "sym-lib-table"
    if not table_path.is_file():
        return {}
    root = parse_sexpr(table_path.read_text(encoding="utf-8", errors="replace"))
    libraries: dict[str, ProjectLibrary] = {}
    for library_node in children(root, "lib"):
        name = atom(child(library_node, "name"), 1)
        uri = atom(child(library_node, "uri"), 1)
        if not name or not uri:
            continue
        expanded = expand_kicad_uri(uri, schematic_dir)
        if expanded.lower().startswith("file://"):
            raw_path = unquote(urlparse(expanded).path)
            if re.match(r"^/[A-Za-z]:/", raw_path):
                raw_path = raw_path[1:]
            candidate = Path(raw_path)
            resolved_path = str(candidate.resolve())
            exists = candidate.is_file()
        elif re.match(r"^[A-Za-z]+://", expanded):
            resolved_path = None
            exists = False
        else:
            candidate = Path(expanded)
            if not candidate.is_absolute():
                candidate = schematic_dir / candidate
            resolved_path = str(candidate.resolve())
            exists = candidate.is_file()
        definitions: tuple[LibrarySymbol, ...] = ()
        if exists and resolved_path:
            definitions = parse_symbol_definitions(Path(resolved_path))
        libraries[name] = ProjectLibrary(
            name,
            uri,
            resolved_path,
            exists,
            tuple(item.name for item in definitions),
            definitions,
        )
    return libraries


def load_json(path: Path | None, default: dict[str, object]) -> dict[str, object]:
    if path is None or not path.is_file():
        return default
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def standard_name_pattern(name: str) -> re.Pattern[str]:
    parts: list[str] = []
    for char in name:
        if not char.isalnum():
            continue
        parts.append("[A-Z0-9]" if char == "x" else re.escape(char.upper()))
    return re.compile("^" + "".join(parts) + "$")


def model_candidates(value: str, index: StandardIndex, similarity: float) -> tuple[list[str], list[str]]:
    normalized = normalize_model(value)
    if not normalized:
        return [], []
    exact: list[str] = []
    fuzzy: list[tuple[float, str]] = []
    for lib_id, name in index.names:
        candidate = normalize_model(name)
        if candidate == normalized or standard_name_pattern(name).fullmatch(normalized):
            exact.append(lib_id)
            continue
        if not candidate or candidate[:4] != normalized[:4] or abs(len(candidate) - len(normalized)) > 5:
            continue
        ratio = SequenceMatcher(None, candidate, normalized).ratio()
        if ratio >= similarity:
            fuzzy.append((ratio, lib_id))
    exact = sorted(set(exact))[:8]
    fuzzy_ids = [lib_id for _, lib_id in sorted(fuzzy, reverse=True)[:8]]
    return exact, fuzzy_ids


def default_category_candidates(prefix: str, pin_count: int) -> tuple[str, ...]:
    mapping = {
        "R": ("Device:R", "Device:R_Small"),
        "C": ("Device:C", "Device:C_Small", "Device:C_Polarized"),
        "D": ("Device:D", "Device:D_TVS", "Device:LED"),
        "Q": ("Transistor_FET:Q_NMOS_GDS", "Transistor_FET:Q_PMOS_GDS"),
        "L": ("Device:L", "Device:L_Small"),
        "FB": ("Device:FerriteBead", "Device:FerriteBead_Small"),
        "F": ("Device:Fuse", "Device:Fuse_Small"),
        "Y": ("Device:Crystal", "Device:Crystal_Small"),
        "X": ("Device:Crystal", "Oscillator:Oscillator_Generic"),
        "SW": ("Switch:SW_Push",),
        "H": ("Mechanical:MountingHole",),
        "MH": ("Mechanical:MountingHole",),
        "TP": ("Connector:TestPoint",),
    }
    if prefix == "J" and 1 <= pin_count <= 99:
        return (f"Connector_Generic:Conn_01x{pin_count:02d}",)
    return mapping.get(prefix, ())


def manifest_entry(manifest: dict[str, object], lib_id: str) -> dict[str, object] | None:
    approved = manifest.get("approved_custom_symbols", {})
    if isinstance(approved, dict) and isinstance(approved.get(lib_id), dict):
        return approved[lib_id]
    return None


def valid_datasheet(value: str) -> bool:
    return bool(value.strip()) and value.strip() != "~"


def record_pin_map(record: SymbolRecord) -> dict[str, tuple[str, str]]:
    return {
        number_value: (name, pin_type)
        for number_value, name, pin_type in zip(record.pin_numbers, record.pin_names, record.pin_types)
    }


def record_from_library(record: SymbolRecord, definition: LibrarySymbol) -> SymbolRecord:
    return replace(
        record,
        pin_count=len(definition.pin_numbers),
        pin_numbers=definition.pin_numbers,
        pin_names=definition.pin_names,
        pin_types=definition.pin_types,
        pin_conflicts=definition.pin_conflicts,
    )


def approved_custom_findings(record: SymbolRecord, entry: dict[str, object]) -> list[SymbolFinding]:
    findings: list[SymbolFinding] = []

    def error(rule: str, message: str) -> None:
        findings.append(SymbolFinding(rule, "error", True, record.reference, record.lib_id, message))

    if not str(entry.get("reason", "")).strip():
        error("custom-symbol-reason-missing", "Approved custom symbol has no reason")
    manifest_datasheet = str(entry.get("datasheet", "")).strip()
    if not valid_datasheet(manifest_datasheet) or not valid_datasheet(record.datasheet):
        error("custom-symbol-datasheet-missing", "Approved custom symbol requires a valid datasheet")
    if not record.footprint.strip():
        error("custom-symbol-footprint-missing", "Approved custom symbol instance has no footprint")
    if not bool(entry.get("pins_reviewed")):
        error("custom-symbol-pins-unreviewed", "Custom symbol pins have not been reviewed")
    if not bool(entry.get("footprint_reviewed")):
        error("custom-symbol-footprint-unreviewed", "Custom symbol footprint has not been reviewed")
    expected_pin_count = entry.get("pin_count")
    if not isinstance(expected_pin_count, int) or expected_pin_count != record.pin_count:
        error(
            "custom-symbol-pin-count-mismatch",
            f"Manifest pin_count {expected_pin_count!r} does not match schematic pin count {record.pin_count}",
        )
    if record.pin_conflicts:
        error(
            "custom-symbol-conflicting-pin-number",
            f"Custom symbol reuses pin numbers with conflicting definitions: {', '.join(record.pin_conflicts)}",
        )
    prefix = reference_prefix(record.reference)
    if prefix == "U" and record.pin_count > 2:
        useful_names = [name for name in record.pin_names if name and not name.isdigit()]
        if len(useful_names) < max(1, record.pin_count // 3):
            error("custom-symbol-pin-names-weak", "Custom IC pin names are missing or mostly numeric")
        meaningful_types = {item for item in record.pin_types if item not in {"passive", "no_connect"}}
        if not meaningful_types:
            error("custom-symbol-pin-types-weak", "Custom IC pins are all passive or unspecified")
    return findings


def evaluate_symbol_policy(
    records: Iterable[SymbolRecord],
    standard_index: StandardIndex | None,
    project_libraries: dict[str, ProjectLibrary],
    policy: dict[str, object],
    manifest: dict[str, object],
) -> tuple[list[dict[str, object]], list[SymbolFinding], dict[str, object]]:
    records = list(records)
    findings: list[SymbolFinding] = []
    results: list[dict[str, object]] = []
    mandatory = {str(item).upper() for item in policy.get("mandatory_standard_prefixes", [])}
    similarity = float(policy.get("candidate_similarity_threshold", 0.88))
    style = str(manifest.get("resistor_style", policy.get("resistor_style", "iec"))).lower()
    iec_symbols = set(policy.get("iec_resistor_symbols", []))
    us_symbols = set(policy.get("us_resistor_symbols", []))

    if standard_index is None:
        findings.append(
            SymbolFinding(
                "standard-library-unavailable",
                "error",
                True,
                "",
                "",
                "KiCad standard symbol directory could not be located",
            )
        )

    for record in records:
        namespace, _ = split_lib_id(record.lib_id)
        prefix = reference_prefix(record.reference)
        is_standard = standard_index is not None and record.lib_id in standard_index.symbols
        entry = manifest_entry(manifest, record.lib_id)
        record_findings: list[SymbolFinding] = []
        candidates: tuple[str, ...] = ()
        source = "standard" if is_standard else "custom"
        status = "standard" if is_standard else "unreviewed_custom"
        source_definition: LibrarySymbol | None = None
        quality_record = record
        cache_consistent: bool | None = None

        if is_standard:
            if style == "iec" and record.lib_id in us_symbols:
                record_findings.append(
                    SymbolFinding(
                        "resistor-style-mismatch",
                        "warning",
                        True,
                        record.reference,
                        record.lib_id,
                        "US zigzag resistor used while project policy requires IEC",
                        tuple(sorted(iec_symbols)),
                    )
                )
                status = "style_warning"
            elif style == "us" and record.lib_id in iec_symbols:
                record_findings.append(
                    SymbolFinding(
                        "resistor-style-mismatch",
                        "warning",
                        True,
                        record.reference,
                        record.lib_id,
                        "IEC resistor used while project policy requires US zigzag style",
                        tuple(sorted(us_symbols)),
                    )
                )
                status = "style_warning"
        else:
            project_library = project_libraries.get(namespace)
            symbol_name = split_lib_id(record.lib_id)[1]
            source_blocked = False
            if project_library is None:
                record_findings.append(
                    SymbolFinding(
                        "embedded-custom-symbol",
                        "error",
                        True,
                        record.reference,
                        record.lib_id,
                        "Custom symbol is only available from the schematic cache; declare a project library in sym-lib-table",
                    )
                )
                source = "embedded"
                status = "violation"
                source_blocked = True
            elif not project_library.exists:
                record_findings.append(
                    SymbolFinding(
                        "custom-library-missing",
                        "error",
                        True,
                        record.reference,
                        record.lib_id,
                        f"Project symbol library does not exist: {project_library.path or project_library.uri}",
                    )
                )
                source = "missing_project_library"
                status = "violation"
                source_blocked = True
            elif symbol_name not in project_library.symbols:
                record_findings.append(
                    SymbolFinding(
                        "custom-symbol-not-in-library",
                        "error",
                        True,
                        record.reference,
                        record.lib_id,
                        "Custom symbol is absent from the project library and only survives in the schematic cache",
                    )
                )
                source = "embedded"
                status = "violation"
                source_blocked = True
            else:
                source = "project"
                source_definition = project_library.definition(symbol_name)
                if source_definition is not None:
                    quality_record = record_from_library(record, source_definition)
                    cache_consistent = (
                        record_pin_map(record) == record_pin_map(quality_record)
                        and tuple(record.pin_conflicts) == tuple(quality_record.pin_conflicts)
                    )
                    if not cache_consistent:
                        record_findings.append(
                            SymbolFinding(
                                "custom-symbol-cache-mismatch",
                                "error",
                                True,
                                record.reference,
                                record.lib_id,
                                "Project library pin definition differs from the schematic lib_symbols cache; resave the schematic",
                            )
                        )
                        status = "violation"
                        source_blocked = True

            exact: list[str] = []
            fuzzy: list[str] = []
            if standard_index is not None:
                exact, fuzzy = model_candidates(record.value or split_lib_id(record.lib_id)[1], standard_index, similarity)
            category_candidates = default_category_candidates(prefix, quality_record.pin_count)
            candidates = tuple(dict.fromkeys(exact + list(category_candidates) + fuzzy))
            override = bool(entry and entry.get("override_standard_candidate"))
            override_reason = str(entry.get("override_reason", "")).strip() if entry else ""

            if record.reference.startswith("#") and namespace != "power":
                record_findings.append(
                    SymbolFinding(
                        "power-symbol-required",
                        "error",
                        True,
                        record.reference,
                        record.lib_id,
                        "Power objects must use the KiCad power library",
                        ("power:*",),
                    )
                )
                status = "violation"
            elif prefix in mandatory:
                record_findings.append(
                    SymbolFinding(
                        "standard-symbol-required",
                        "error",
                        True,
                        record.reference,
                        record.lib_id,
                        f"Reference class {prefix} must use a KiCad standard-library symbol",
                        candidates,
                    )
                )
                status = "violation"
            elif exact and not (override and override_reason):
                record_findings.append(
                    SymbolFinding(
                        "standard-symbol-available",
                        "error",
                        True,
                        record.reference,
                        record.lib_id,
                        "An exact or KiCad-wildcard standard symbol is available",
                        tuple(exact),
                    )
                )
                status = "violation"
            elif fuzzy and entry is None:
                record_findings.append(
                    SymbolFinding(
                        "standard-symbol-candidate",
                        "warning",
                        True,
                        record.reference,
                        record.lib_id,
                        "Similar standard symbols require human review",
                        tuple(fuzzy),
                    )
                )
                status = "candidate_review"
            elif entry is None:
                record_findings.append(
                    SymbolFinding(
                        "custom-symbol-unregistered",
                        "warning",
                        True,
                        record.reference,
                        record.lib_id,
                        "Custom symbol is not registered in the project symbol manifest",
                    )
                )
                status = "manifest_required"
            else:
                quality_findings = approved_custom_findings(quality_record, entry)
                record_findings.extend(quality_findings)
                if quality_findings:
                    status = "custom_quality_failure"
                elif override and override_reason:
                    record_findings.append(
                        SymbolFinding(
                            "custom-symbol-approved-exception",
                            "warning",
                            False,
                            record.reference,
                            record.lib_id,
                            f"User-approved standard-symbol exception: {override_reason}",
                            candidates,
                        )
                    )
                    status = "approved_exception"
                else:
                    status = "approved_custom"

            if source_blocked:
                status = "violation"

        findings.extend(record_findings)
        results.append(
            {
                "reference": record.reference,
                "value": record.value,
                "lib_id": record.lib_id,
                "footprint": record.footprint,
                "datasheet": record.datasheet,
                "description": record.description,
                "cache_pin_count": record.pin_count,
                "source_pin_count": quality_record.pin_count if source_definition else None,
                "source_pin_conflicts": list(quality_record.pin_conflicts) if source_definition else [],
                "source": source,
                "status": status,
                "cache_consistent": cache_consistent,
                "candidates": list(candidates),
                "findings": [asdict(item) for item in record_findings],
            }
        )

    summary = {
        "instances": len(records),
        "standard": sum(item["source"] == "standard" for item in results),
        "project_custom": sum(item["source"] == "project" for item in results),
        "embedded_custom": sum(item["source"] == "embedded" for item in results),
        "approved_custom": sum(item["status"] == "approved_custom" for item in results),
        "approved_exceptions": sum(item["status"] == "approved_exception" for item in results),
        "errors": sum(item.severity == "error" for item in findings),
        "warnings": sum(item.severity == "warning" for item in findings),
        "blocking": sum(item.blocking for item in findings),
    }
    return results, findings, summary
