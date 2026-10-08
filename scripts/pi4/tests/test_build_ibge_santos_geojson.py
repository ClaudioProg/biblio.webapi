import importlib.util
import json
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "build_ibge_santos_geojson.py"
SPEC = importlib.util.spec_from_file_location("build_ibge_santos_geojson", MODULE_PATH)
geo = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(geo)

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / "data" / "pi4" / "ibge_santos_bairros.geojson"


class IbgeGeoDataTests(unittest.TestCase):
    def test_round_coordinates_preserves_structure(self):
        value = [[[-46.123456789, -23.987654321], [-46.1, -23.9]]]
        rounded = geo.round_coordinates(value)
        self.assertEqual(rounded[0][0], [-46.1234568, -23.9876543])

    def test_snapshot_has_55_features_and_unique_codes(self):
        with SNAPSHOT.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        self.assertEqual(data["type"], "FeatureCollection")
        self.assertEqual(len(data["features"]), 55)

        codes = [
            feature["properties"]["cd_bairro"]
            for feature in data["features"]
        ]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(all(code.startswith("3548500") for code in codes))

    def test_snapshot_codes_match_analytical_csv(self):
        with SNAPSHOT.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        geometry_codes = {
            feature["properties"]["cd_bairro"]
            for feature in data["features"]
        }
        self.assertEqual(geometry_codes, geo.analytical_codes())

    def test_snapshot_contains_paqueta_with_geometry(self):
        with SNAPSHOT.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        paqueta = next(
            feature
            for feature in data["features"]
            if feature["properties"]["cd_bairro"] == "3548500016"
        )
        self.assertEqual(paqueta["properties"]["bairro"], "Paquetá")
        self.assertIn(paqueta["geometry"]["type"], {"Polygon", "MultiPolygon"})
        self.assertTrue(paqueta["geometry"]["coordinates"])


if __name__ == "__main__":
    unittest.main()
