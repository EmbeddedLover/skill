#!/usr/bin/env python3
"""Regression tests for the deterministic KiCad visual audit rules."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

import audit_schematic as audit


def schematic_with(content: str) -> list[audit.SExpr]:
    return audit.parse_sexpr(
        f"""
        (kicad_sch
          (paper "A4")
          (lib_symbols
            (symbol "Test:Box"
              (symbol "Box_0_1"
                (rectangle (start -2 -2) (end 2 2)))))
          {content})
        """
    )


def run_audit(root: list[audit.SExpr]) -> tuple[list[audit.Issue], dict[str, object]]:
    return audit.run_visual_audit(
        root,
        text_clearance=0.35,
        symbol_clearance=1.27,
        module_clearance=1.27,
        page_margin=5.0,
        minimum_frame_area=180.0,
        density_cell=2.54,
        max_module_density=0.62,
        max_zone_density=0.72,
        max_items_per_1000=55.0,
        title_block_width=115.0,
        title_block_height=40.0,
    )


def check_args(**overrides: object) -> SimpleNamespace:
    values = {
        "profile": "full",
        "checks": None,
        "skip_cli": False,
        "strict_symbol_policy": False,
        "symbol_report": None,
        "fail_on_visual": False,
        "fail_on_visual_warnings": False,
        "visual_report": None,
        "max_wire_mm": None,
        "expect_net": [],
        "render_png": False,
        "require_cli": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class VisualAuditTests(unittest.TestCase):
    def test_page_without_module_frames_is_audited_without_crashing(self) -> None:
        root = schematic_with(
            """
            (symbol
              (lib_id "Test:Box") (at 40 40 0)
              (property "Reference" "U1" (at 40 35 0) (effects (font (size 1 1)))))
            """
        )
        _, summary = run_audit(root)
        self.assertEqual(summary["module_frames"], 0)

    def test_nested_effects_hide_marks_property_invisible(self) -> None:
        hidden = audit.parse_sexpr(
            '(property "Footprint" "Package:Part" (effects (font (size 1 1)) (hide yes)))'
        )
        shown = audit.parse_sexpr('(property "Value" "10k" (effects (font (size 1 1))))')
        self.assertFalse(audit.visible(hidden))
        self.assertTrue(audit.visible(shown))

    def test_profiles_select_only_required_checks(self) -> None:
        self.assertEqual(audit.resolve_checks(check_args(profile="symbol")), frozenset({"symbol"}))
        self.assertEqual(audit.resolve_checks(check_args(profile="visual")), frozenset({"visual", "wires"}))
        self.assertEqual(audit.resolve_checks(check_args(profile="electrical")), frozenset({"wires", "cli"}))

    def test_explicit_checks_override_profile_and_validation_flags_add_dependencies(self) -> None:
        selected = audit.resolve_checks(
            check_args(profile="full", checks="symbol", fail_on_visual=True, expect_net=["N=U1:1"])
        )
        self.assertEqual(selected, frozenset({"symbol", "visual", "cli"}))
        with self.assertRaises(ValueError):
            audit.resolve_checks(check_args(checks="symbol,unknown"))

    def test_visual_errors_and_warnings_have_separate_failure_controls(self) -> None:
        issues = [
            audit.Issue("overlap", "error", "error", ("A", "B")),
            audit.Issue("clearance", "warning", "warning", ("A", "B")),
        ]
        self.assertEqual(audit.visual_gate_failures(issues, True, False), ["visual errors found"])
        self.assertEqual(
            audit.visual_gate_failures(issues, True, True),
            ["visual errors found", "visual warnings found"],
        )

    def test_detects_overlap_duplicate_wire_frame_crossing_and_title_block(self) -> None:
        root = schematic_with(
            """
            (rectangle (start 20 20) (end 80 70))
            (symbol
              (lib_id "Test:Box") (at 40 40 0)
              (property "Reference" "U1" (at 40 35 0) (effects (font (size 1 1)))))
            (symbol
              (lib_id "Test:Box") (at 42 40 0)
              (property "Reference" "U2" (at 42 35 0) (effects (font (size 1 1)))))
            (text "collision" (at 40 40 0) (effects (font (size 1 1))))
            (text "edge" (at 20 30 0) (effects (font (size 1 1)) (justify left)))
            (text "title intrusion" (at 220 180 0) (effects (font (size 1 1))))
            (wire (pts (xy 10 40) (xy 90 40)) (uuid "wire-one"))
            (wire (pts (xy 10 40) (xy 90 40)) (uuid "wire-two"))
            """
        )
        issues, summary = run_audit(root)
        rules = {issue.rule for issue in issues}
        self.assertIn("symbol-overlap", rules)
        self.assertIn("duplicate-wire", rules)
        self.assertIn("wire-through-symbol", rules)
        self.assertIn("wire-crosses-module-frame", rules)
        self.assertIn("module-frame-through-content", rules)
        self.assertIn("title-block-intrusion", rules)
        overlap = next(issue for issue in issues if issue.rule == "symbol-overlap")
        self.assertEqual(overlap.message, "Symbol bodies overlap")
        frame_collision = next(issue for issue in issues if issue.rule == "module-frame-through-content")
        self.assertAlmostEqual(frame_collision.location[0], 20.0)
        self.assertEqual(summary["wires"], 2)
        self.assertEqual(summary["unique_wires"], 1)

    def test_reconstructs_frame_from_four_polyline_segments(self) -> None:
        root = schematic_with(
            """
            (polyline (pts (xy 20 20) (xy 80 20)))
            (polyline (pts (xy 80 20) (xy 80 70)))
            (polyline (pts (xy 80 70) (xy 20 70)))
            (polyline (pts (xy 20 70) (xy 20 20)))
            (symbol
              (lib_id "Test:Box") (at 40 40 0)
              (property "Reference" "U1" (at 40 35 0) (effects (font (size 1 1)))))
            """
        )
        _, summary = run_audit(root)
        self.assertEqual(summary["module_frames"], 1)

    def test_closed_polyline_frame_keeps_its_identity(self) -> None:
        root = schematic_with(
            """
            (polyline
              (pts (xy 20 20) (xy 80 20) (xy 80 70) (xy 20 70) (xy 20 20))
              (uuid "12345678-1234-1234-1234-123456789abc"))
            """
        )
        frames = audit.extract_frames(root, minimum_area=180.0)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].identity, "polyline:12345678")

    def test_clean_geometry_avoids_core_collision_rules(self) -> None:
        root = schematic_with(
            """
            (rectangle (start 20 20) (end 80 70))
            (symbol
              (lib_id "Test:Box") (at 40 45 0)
              (property "Reference" "U1" (at 40 39 0) (effects (font (size 1 1)))))
            (text "MODULE" (at 25 25 0) (effects (font (size 1 1)) (justify left top)))
            """
        )
        issues, _ = run_audit(root)
        rules = {issue.rule for issue in issues}
        self.assertNotIn("symbol-overlap", rules)
        self.assertNotIn("text-collision", rules)
        self.assertNotIn("wire-through-symbol", rules)
        self.assertNotIn("wire-crosses-module-frame", rules)

    def test_pin_edge_label_is_allowed_but_label_inside_symbol_is_reported(self) -> None:
        root = schematic_with(
            """
            (symbol
              (lib_id "Test:Box") (at 40 40 0)
              (property "Reference" "U1" (at 40 35 0) (effects (font (size 1 1)))))
            (label "PIN_NET" (at 41.8 40 0) (effects (font (size 1 1))))
            (label "BAD_NET" (at 40 40 0) (effects (font (size 1 1))))
            """
        )
        issues, _ = run_audit(root)
        collisions = [issue for issue in issues if issue.rule == "text-symbol-collision"]
        self.assertTrue(any("label:BAD_NET" in issue.objects[0] for issue in collisions))
        self.assertFalse(any("label:PIN_NET" in issue.objects[0] for issue in collisions))


if __name__ == "__main__":
    unittest.main()
