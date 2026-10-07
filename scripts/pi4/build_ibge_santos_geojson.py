#!/usr/bin/env python3
"""Generate the Santos neighborhood GeoJSON from the official IBGE shapefile."""

from __future__ import annotations

import argparse
import csv
import io
import json
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import shapefile

MUNICIPALITY_CODE = "3548500"
EXPECTED_NEIGHBORHOODS = 70
USER_AGENT = "BibliotecasConectadas-PI4/1.0"

ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANIFEST = ROOT / "docs" / "pi4" / "ibge-sources.json"
ANALYTICAL_CSV = ROOT / "data" / "pi4" / "ibge_santos_bairros.csv"
DEFAULT_OUTPUT = ROOT / "data" / "pi4" / "ibge_santos_bairros.geojson"


class GeoDataError(RuntimeError):
    """Raised when the official geometry cannot be validated."""


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def download_bytes(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def analytical_codes(path: Path = ANALYTICAL_CSV) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["cd_bairro"] for row in csv.DictReader(handle)}


def round_coordinates(value: Any, digits: int = 7) -> Any:
    if isinstance(value, (list, tuple)):
        if (
            len(value) >= 2
            and all(isinstance(item, (int, float)) for item in value[:2])
        ):
            return [round(float(item), digits) for item in value]
        return [round_coordinates(item, digits=digits) for item in value]
    return value


def source_url(manifest: dict[str, Any]) -> str:
    for item in manifest.get("geodata", []):
        if item.get("id") == "bairros_sp_shapefile":
            return str(item["url"])
    raise GeoDataError("Fonte geográfica bairros_sp_shapefile não encontrada no manifesto.")


def build_feature(record: dict[str, Any], geometry: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "cd_bairro": str(record["CD_BAIRRO"]),
            "bairro": str(record["NM_BAIRRO"]),
            "area_km2": float(record["AREA_KM2"]),
        },
        "geometry": {
            "type": geometry["type"],
            "coordinates": round_coordinates(geometry["coordinates"]),
        },
    }


def generate_geojson(
    shapefile_zip: bytes,
    expected_codes: set[str],
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp_dir:
        archive = zipfile.ZipFile(io.BytesIO(shapefile_zip))
        archive.extractall(temp_dir)

        shp_names = [name for name in archive.namelist() if name.lower().endswith(".shp")]
        if len(shp_names) != 1:
            raise GeoDataError(
                f"Esperado um único .shp no ZIP; encontrados {len(shp_names)}."
            )

        shp_path = Path(temp_dir) / shp_names[0]
        reader = shapefile.Reader(str(shp_path), encoding="utf-8")
        field_names = [field[0] for field in reader.fields[1:]]

        features: list[dict[str, Any]] = []
        shape_codes: set[str] = set()

        for shape_record in reader.iterShapeRecords():
            record = dict(zip(field_names, shape_record.record))
            if str(record.get("CD_MUN", "")) != MUNICIPALITY_CODE:
                continue

            code = str(record["CD_BAIRRO"])
            if code in shape_codes:
                raise GeoDataError(f"Código de bairro duplicado na malha: {code}.")

            shape_codes.add(code)
            features.append(
                build_feature(record, shape_record.shape.__geo_interface__)
            )

    if len(features) != EXPECTED_NEIGHBORHOODS:
        raise GeoDataError(
            f"Esperados {EXPECTED_NEIGHBORHOODS} bairros; encontrados {len(features)}."
        )

    missing = sorted(expected_codes - shape_codes)
    extra = sorted(shape_codes - expected_codes)
    if missing or extra:
        raise GeoDataError(
            f"Códigos da malha divergentes do snapshot analítico. "
            f"Ausentes={missing}; extras={extra}."
        )

    features.sort(key=lambda feature: feature["properties"]["cd_bairro"])

    return {
        "type": "FeatureCollection",
        "name": "Santos — Bairros — Censo Demográfico 2022",
        "metadata": {
            "source": "IBGE — Censo Demográfico 2022",
            "municipality": "Santos",
            "state": "SP",
            "municipality_ibge_code": MUNICIPALITY_CODE,
            "source_crs": "EPSG:4674",
            "source_crs_name": "SIRGAS 2000",
            "personal_data": False,
        },
        "features": features,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    manifest = read_json(SOURCE_MANIFEST)
    expected_codes = analytical_codes()
    if len(expected_codes) != EXPECTED_NEIGHBORHOODS:
        raise GeoDataError(
            f"Snapshot analítico possui {len(expected_codes)} códigos; "
            f"esperados {EXPECTED_NEIGHBORHOODS}."
        )

    content = download_bytes(source_url(manifest))
    geojson = generate_geojson(content, expected_codes)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(geojson, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")

    print(
        f"OK: {len(geojson['features'])} bairros de Santos; "
        f"GeoJSON em {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
