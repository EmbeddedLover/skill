#!/usr/bin/env python3
"""Regression tests for KiCad standard-symbol provenance policy."""

from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

import symbol_policy as policy


POLICY = {
    "version": 1,
    "resistor_style": "iec",
    "candidate_similarity_threshold": 0.88,
    "mandatory_standard_prefixes": ["R", "C", "D", "Q", "L", "FB", "F", "Y", "X", "SW", "J", "H", "MH", "TP"],
    "iec_resistor_symbols": ["Device:R", "Device:R_Small"],
    "us_resistor_symbols": ["Device:R_US", "Device:R_US_Small"],
}

INDEX = policy.StandardIndex(
    root="standard",
    symbols=frozenset(
        {
            "Device:R",
            "Device:C",
            "Device:D",
            "Device:LED",
            "Device:Crystal",
            "Device:R_US",
            "Transistor_FET:Q_NMOS_GDS",
            "Connector_Generic:Conn_01x05",
            "Interface_CAN_LIN:SN65HVD230",
            "Regulator_Linear:TLV75533PDBV",
            "MCU_ST_STM32G4:STM32G431CBTx",
        }
    ),
    names=(
        ("Device:R", "R"),
        ("Device:C", "C"),
        ("Device:D", "D"),
        ("Device:LED", "LED"),
        ("Device:Crystal", "Crystal"),
        ("Device:R_US", "R_US"),
        ("Transistor_FET:Q_NMOS_GDS", "Q_NMOS_GDS"),
        ("Connector_Generic:Conn_01x05", "Conn_01x05"),
        ("Interface_CAN_LIN:SN65HVD230", "SN65HVD230"),
        ("Regulator_Linear:TLV75533PDBV", "TLV75533PDBV"),
        ("MCU_ST_STM32G4:STM32G431CBTx", "STM32G431CBTx"),
    ),
    libraries=frozenset(
        {"Device", "Transistor_FET", "Connector_Generic", "Interface_CAN_LIN", "Regulator_Linear", "MCU_ST_STM32G4"}
    ),
)

PROJECT_LIBRARIES = {
    "FOC": policy.ProjectLibrary(
        "FOC",
        "${KIPRJMOD}/FOC.kicad_sym",
        "C:/project/FOC.kicad_sym",
        True,
        ("R", "C", "CONN5", "SN65HVD230", "TLV75533PDBV", "STM32G431CBT6", "DRV8353RSRGZR"),
    )
}


def record(
    reference: str,
    value: str,
    lib_id: str,
    pin_count: int = 2,
    footprint: str = "Package:Footprint",
    datasheet: str = "https://example.com/datasheet.pdf",
) -> policy.SymbolRecord:
    numbers = tuple(str(index) for index in range(1, pin_count + 1))
    names = tuple(f"PIN_{index}" for index in range(1, pin_count + 1))
    types = tuple("bidirectional" for _ in range(pin_count))
    return policy.SymbolRecord(
        reference,
        value,
        lib_id,
        footprint,
        datasheet,
        "test symbol",
        pin_count,
        numbers,
        names,
        types,
    )


def evaluate(records: list[policy.SymbolRecord], manifest: dict[str, object] | None = None):
    return policy.evaluate_symbol_policy(records, INDEX, PROJECT_LIBRARIES, POLICY, manifest or {"version": 1})


class SymbolPolicyTests(unittest.TestCase):
    def test_standard_discretes_and_connector_pass(self) -> None:
        records = [
            record("R1", "10k", "Device:R"),
            record("C1", "100nF", "Device:C"),
            record("D1", "1N4148", "Device:D"),
            record("D2", "GREEN", "Device:LED"),
            record("Y1", "8MHz", "Device:Crystal"),
            record("Q1", "MOSFET", "Transistor_FET:Q_NMOS_GDS", 3),
            record("J1", "SWD", "Connector_Generic:Conn_01x05", 5),
        ]
        _, findings, summary = evaluate(records)
        self.assertEqual(findings, [])
        self.assertEqual(summary["standard"], len(records))

    def test_custom_discrete_and_connector_are_violations(self) -> None:
        records = [record("R1", "10k", "FOC:R"), record("C1", "100nF", "FOC:C"), record("J1", "SWD", "FOC:CONN5", 5)]
        _, findings, summary = evaluate(records)
        self.assertEqual(sum(item.rule == "standard-symbol-required" for item in findings), 3)
        self.assertEqual(summary["blocking"], 3)

    def test_exact_and_wildcard_ic_candidates_are_violations(self) -> None:
        records = [
            record("U1", "SN65HVD230", "FOC:SN65HVD230", 8),
            record("U2", "TLV75533PDBV", "FOC:TLV75533PDBV", 5),
            record("U3", "STM32G431CBT6", "FOC:STM32G431CBT6", 48),
        ]
        _, findings, _ = evaluate(records)
        matches = [item for item in findings if item.rule == "standard-symbol-available"]
        self.assertEqual(len(matches), 3)
        self.assertTrue(any("STM32G431CBTx" in candidate for item in matches for candidate in item.candidates))

    def test_unknown_custom_ic_requires_manifest(self) -> None:
        _, findings, summary = evaluate([record("U1", "DRV8353RSRGZR", "FOC:DRV8353RSRGZR", 49)])
        self.assertTrue(any(item.rule == "custom-symbol-unregistered" for item in findings))
        self.assertEqual(summary["blocking"], 1)

    def test_reviewed_custom_ic_passes(self) -> None:
        manifest = {
            "version": 1,
            "approved_custom_symbols": {
                "FOC:DRV8353RSRGZR": {
                    "reason": "No exact KiCad symbol",
                    "datasheet": "https://example.com/drv8353.pdf",
                    "pin_count": 49,
                    "pins_reviewed": True,
                    "footprint_reviewed": True,
                }
            },
        }
        results, findings, summary = evaluate([record("U1", "DRV8353RSRGZR", "FOC:DRV8353RSRGZR", 49)], manifest)
        self.assertEqual(findings, [])
        self.assertEqual(results[0]["status"], "approved_custom")
        self.assertEqual(summary["approved_custom"], 1)

    def test_manifest_pin_count_and_review_fields_are_enforced(self) -> None:
        manifest = {
            "version": 1,
            "approved_custom_symbols": {
                "FOC:DRV8353RSRGZR": {
                    "reason": "No exact KiCad symbol",
                    "datasheet": "https://example.com/drv8353.pdf",
                    "pin_count": 48,
                    "pins_reviewed": False,
                    "footprint_reviewed": False,
                }
            },
        }
        _, findings, _ = evaluate([record("U1", "DRV8353RSRGZR", "FOC:DRV8353RSRGZR", 49)], manifest)
        rules = {item.rule for item in findings}
        self.assertIn("custom-symbol-pin-count-mismatch", rules)
        self.assertIn("custom-symbol-pins-unreviewed", rules)
        self.assertIn("custom-symbol-footprint-unreviewed", rules)

    def test_us_resistor_warns_under_iec_policy(self) -> None:
        _, findings, summary = evaluate([record("R1", "10k", "Device:R_US")])
        self.assertEqual(findings[0].rule, "resistor-style-mismatch")
        self.assertTrue(findings[0].blocking)
        self.assertEqual(summary["blocking"], 1)

    def test_embedded_custom_symbol_is_blocking(self) -> None:
        results, findings, _ = policy.evaluate_symbol_policy(
            [record("U1", "CUSTOM123", "Embedded:CUSTOM123", 8)], INDEX, {}, POLICY, {"version": 1}
        )
        self.assertTrue(any(item.rule == "embedded-custom-symbol" for item in findings))
        self.assertEqual(results[0]["status"], "violation")

    def test_symbol_missing_from_declared_project_library_is_blocking(self) -> None:
        libraries = {
            "FOC": policy.ProjectLibrary("FOC", "${KIPRJMOD}/FOC.kicad_sym", "C:/project/FOC.kicad_sym", True, ("OTHER",))
        }
        _, findings, _ = policy.evaluate_symbol_policy(
            [record("U1", "DRV8353RSRGZR", "FOC:DRV8353RSRGZR", 49)], INDEX, libraries, POLICY, {"version": 1}
        )
        self.assertTrue(any(item.rule == "custom-symbol-not-in-library" for item in findings))

    def test_missing_standard_index_is_blocking(self) -> None:
        _, findings, summary = policy.evaluate_symbol_policy(
            [record("R1", "10k", "Device:R")], None, {}, POLICY, {"version": 1}
        )
        self.assertTrue(any(item.rule == "standard-library-unavailable" for item in findings))
        self.assertGreater(summary["blocking"], 0)

    def test_explicit_user_override_is_reported_but_not_blocking(self) -> None:
        manifest = {
            "version": 1,
            "approved_custom_symbols": {
                "FOC:SN65HVD230": {
                    "reason": "Validated project variant",
                    "datasheet": "https://example.com/sn65hvd230.pdf",
                    "pin_count": 8,
                    "pins_reviewed": True,
                    "footprint_reviewed": True,
                    "override_standard_candidate": True,
                    "override_reason": "User approved a reviewed project symbol",
                }
            },
        }
        results, findings, summary = evaluate([record("U1", "SN65HVD230", "FOC:SN65HVD230", 8)], manifest)
        self.assertEqual(results[0]["status"], "approved_exception")
        self.assertTrue(any(item.rule == "custom-symbol-approved-exception" for item in findings))
        self.assertEqual(summary["blocking"], 0)

    def test_override_cannot_bypass_mandatory_standard_discrete(self) -> None:
        manifest = {
            "version": 1,
            "approved_custom_symbols": {
                "FOC:R": {
                    "reason": "Project resistor graphic",
                    "datasheet": "https://example.com/resistor.pdf",
                    "pin_count": 2,
                    "pins_reviewed": True,
                    "footprint_reviewed": True,
                    "override_standard_candidate": True,
                    "override_reason": "Requested project graphic",
                }
            },
        }
        _, findings, summary = evaluate([record("R1", "10k", "FOC:R")], manifest)
        self.assertTrue(any(item.rule == "standard-symbol-required" for item in findings))
        self.assertGreater(summary["blocking"], 0)

    def test_override_cannot_bypass_power_library_requirement(self) -> None:
        libraries = {
            **PROJECT_LIBRARIES,
            "FOC": policy.ProjectLibrary(
                "FOC",
                "${KIPRJMOD}/FOC.kicad_sym",
                "C:/project/FOC.kicad_sym",
                True,
                (*PROJECT_LIBRARIES["FOC"].symbols, "+3V3"),
            ),
        }
        manifest = {
            "version": 1,
            "approved_custom_symbols": {
                "FOC:+3V3": {
                    "reason": "Project power graphic",
                    "datasheet": "https://example.com/power.pdf",
                    "pin_count": 1,
                    "pins_reviewed": True,
                    "footprint_reviewed": True,
                    "override_standard_candidate": True,
                    "override_reason": "Requested project graphic",
                }
            },
        }
        _, findings, summary = policy.evaluate_symbol_policy(
            [record("#FLG01", "+3V3", "FOC:+3V3", 1)], INDEX, libraries, POLICY, manifest
        )
        self.assertTrue(any(item.rule == "power-symbol-required" for item in findings))
        self.assertGreater(summary["blocking"], 0)

    def test_project_library_source_definition_is_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "sym-lib-table").write_text(
                '(sym_lib_table (lib (name "FOC") (type "KiCad") (uri "${KIPRJMOD}/FOC.kicad_sym")))',
                encoding="utf-8",
            )
            (project / "FOC.kicad_sym").write_text(
                """
                (kicad_symbol_lib
                  (version 20231120)
                  (symbol "CUSTOM_IC"
                    (symbol "CUSTOM_IC_1_1"
                      (pin input line (name "IN") (number "1"))
                      (pin output line (name "OUT") (number "2")))))
                """,
                encoding="utf-8",
            )
            libraries = policy.parse_project_libraries(project)
            definition = libraries["FOC"].definition("CUSTOM_IC")
            self.assertIsNotNone(definition)
            self.assertEqual(definition.pin_numbers, ("1", "2"))
            self.assertEqual(definition.pin_types, ("input", "output"))

    def test_project_library_and_schematic_cache_mismatch_is_blocking(self) -> None:
        source = policy.LibrarySymbol("CUSTOM_IC", ("1", "2"), ("IN", "OUT"), ("input", "output"))
        libraries = {
            "FOC": policy.ProjectLibrary(
                "FOC", "${KIPRJMOD}/FOC.kicad_sym", "C:/project/FOC.kicad_sym", True, ("CUSTOM_IC",), (source,)
            )
        }
        manifest = {
            "version": 1,
            "approved_custom_symbols": {
                "FOC:CUSTOM_IC": {
                    "reason": "No standard symbol",
                    "datasheet": "https://example.com/custom.pdf",
                    "pin_count": 2,
                    "pins_reviewed": True,
                    "footprint_reviewed": True,
                }
            },
        }
        cached = record("U1", "CUSTOM_IC", "FOC:CUSTOM_IC", 2)
        _, findings, summary = policy.evaluate_symbol_policy([cached], INDEX, libraries, POLICY, manifest)
        self.assertTrue(any(item.rule == "custom-symbol-cache-mismatch" for item in findings))
        self.assertGreater(summary["blocking"], 0)

    def test_standard_index_cache_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "symbols"
            root.mkdir()
            (root / "Device.kicad_sym").write_text(
                '(kicad_symbol_lib\n  (symbol "R"\n    (symbol "R_1_1")))\n', encoding="utf-8"
            )
            cache = Path(directory) / "index.json"
            first = policy.build_standard_index(root, cache)
            second = policy.build_standard_index(root, cache)
            self.assertFalse(first.cache_hit)
            self.assertTrue(second.cache_hit)
            self.assertIn("Device:R", second.symbols)

    def test_duplicate_variant_pins_only_fail_when_definitions_conflict(self) -> None:
        identical = policy.pin_definition(
            "IC",
            [
                ["pin", "input", ["name", "IN"], ["number", "1"]],
                ["pin", "input", ["name", "IN"], ["number", "1"]],
            ],
        )
        conflicting = policy.pin_definition(
            "IC",
            [
                ["pin", "input", ["name", "IN"], ["number", "1"]],
                ["pin", "output", ["name", "OUT"], ["number", "1"]],
            ],
        )
        self.assertEqual(identical.pin_conflicts, ())
        self.assertEqual(conflicting.pin_conflicts, ("1",))


if __name__ == "__main__":
    unittest.main()
