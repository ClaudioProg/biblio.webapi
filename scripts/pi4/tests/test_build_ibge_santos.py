import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "build_ibge_santos.py"
SPEC = importlib.util.spec_from_file_location("build_ibge_santos", MODULE_PATH)
etl = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(etl)


class IbgeEtlTests(unittest.TestCase):
    def test_parse_missing_markers_as_null(self):
        for marker in ("", ".", "x", "X", None):
            self.assertIsNone(etl.parse_int(marker))
            self.assertIsNone(etl.parse_decimal(marker))

    def test_decimal_pt_br_is_normalized(self):
        self.assertEqual(str(etl.parse_decimal("7220,24")), "7220.24")
        self.assertEqual(str(etl.parse_decimal("0,6800466")), "0.6800466")

    def test_strict_sum_is_null_if_any_component_missing(self):
        row = {"A": "10", "B": ".", "C": "5"}
        self.assertIsNone(etl.strict_sum(row, ["A", "B", "C"]))

    def test_strict_sum_adds_complete_components(self):
        row = {"A": "10", "B": "2", "C": "5"}
        self.assertEqual(etl.strict_sum(row, ["A", "B", "C"]), 17)

    def test_municipality_filter_uses_cd_mun_when_available(self):
        rows = [
            {"CD_BAIRRO": "3513504001", "CD_MUN": "3513504", "NM_BAIRRO": "Cubatão"},
            {"CD_BAIRRO": "3548500001", "CD_MUN": "3548500", "NM_BAIRRO": "José Menino"},
        ]
        selected = etl.municipality_rows(rows)
        self.assertEqual(list(selected), ["3548500001"])

    def test_municipality_filter_uses_bairro_prefix_when_cd_mun_absent(self):
        rows = [
            {"CD_BAIRRO": "3513504001", "NM_BAIRRO": "Cubatão"},
            {"CD_BAIRRO": "3548500001", "NM_BAIRRO": "José Menino"},
        ]
        selected = etl.municipality_rows(rows)
        self.assertEqual(list(selected), ["3548500001"])


if __name__ == "__main__":
    unittest.main()
