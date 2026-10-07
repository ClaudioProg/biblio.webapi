#!/usr/bin/env python3
"""Build the PI4 Santos/IBGE neighborhood analytical table.

The script downloads official IBGE CSV ZIP files declared in
docs/pi4/ibge-sources.json, filters Santos (IBGE 3548500), applies the
documented transformations and writes a UTF-8 analytical snapshot for
Power BI and validation.

No reader-level or other personal data are used.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

MUNICIPALITY_CODE = "3548500"
MISSING_MARKERS = {"", ".", "x", "X"}
DEFAULT_TIMEOUT_SECONDS = 60
USER_AGENT = "BibliotecasConectadas-PI4/1.0"

ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANIFEST = ROOT / "docs" / "pi4" / "ibge-sources.json"
VARIABLE_MAP = ROOT / "docs" / "pi4" / "ibge-variable-map.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "pi4"

DATASET_IDS = {
    "basic": "bairro_basico",
    "demography": "bairro_demografia",
    "literacy": "bairro_alfabetizacao",
    "income": "bairro_renda_responsavel",
}


class EtlError(RuntimeError):
    """Raised when an input source or invariant is not suitable for the PI4 table."""


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def download_bytes(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/zip,application/octet-stream,*/*",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def csv_rows_from_zip(content: bytes) -> list[dict[str, str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise EtlError("A fonte baixada não é um ZIP válido.") from exc

    csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
    if len(csv_names) != 1:
        raise EtlError(
            f"Esperado exatamente 1 CSV no ZIP; encontrados {len(csv_names)}."
        )

    raw = archive.read(csv_names[0])
    decoded = None
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            decoded = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if decoded is None:
        raise EtlError("Não foi possível decodificar o CSV do IBGE.")

    return list(csv.DictReader(io.StringIO(decoded), delimiter=";"))


def municipality_rows(
    rows: list[dict[str, str]],
    municipality_code: str = MUNICIPALITY_CODE,
) -> dict[str, dict[str, str]]:
    if not rows:
        return {}

    has_municipality_column = "CD_MUN" in rows[0]
    selected: dict[str, dict[str, str]] = {}

    for row in rows:
        neighborhood_code = str(row.get("CD_BAIRRO") or "").strip()
        if not neighborhood_code:
            continue

        belongs = (
            str(row.get("CD_MUN") or "").strip() == municipality_code
            if has_municipality_column
            else neighborhood_code.startswith(municipality_code)
        )
        if not belongs:
            continue

        if neighborhood_code in selected:
            raise EtlError(f"Código de bairro duplicado: {neighborhood_code}.")
        selected[neighborhood_code] = row

    return selected


def parse_int(value: Any) -> int | None:
    text = str(value or "").strip()
    if text in MISSING_MARKERS:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise EtlError(f"Valor inteiro inesperado: {text!r}.") from exc


def parse_decimal(value: Any) -> Decimal | None:
    text = str(value or "").strip()
    if text in MISSING_MARKERS:
        return None

    normalized = text.replace(".", "").replace(",", ".") if "," in text else text
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise EtlError(f"Valor decimal inesperado: {text!r}.") from exc


def strict_sum(row: dict[str, str], variables: list[str]) -> int | None:
    values = [parse_int(row.get(variable)) for variable in variables]
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def decimal_for_csv(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value, "f")


def validate_required_columns(
    dataset: str,
    rows: dict[str, dict[str, str]],
    required: set[str],
) -> None:
    if not rows:
        raise EtlError(f"Dataset {dataset!r} não retornou bairros de Santos.")

    sample = next(iter(rows.values()))
    missing = sorted(required - set(sample))
    if missing:
        raise EtlError(
            f"Dataset {dataset!r} não contém colunas obrigatórias: {missing}."
        )


def transform(
    datasets: dict[str, dict[str, dict[str, str]]],
    variable_map: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    basic = datasets["basic"]
    demography = datasets["demography"]
    literacy = datasets["literacy"]
    income = datasets["income"]

    basic_codes = set(basic)
    if set(demography) != basic_codes:
        raise EtlError("Demografia e Básico não possuem o mesmo conjunto de bairros.")
    if set(literacy) != basic_codes:
        raise EtlError("Alfabetização e Básico não possuem o mesmo conjunto de bairros.")
    if not set(income).issubset(basic_codes):
        raise EtlError("Renda contém bairro fora da base Básico de Santos.")

    dmap = variable_map["demography"]
    lmap = variable_map["literacy"]
    imap = variable_map["income"]

    result: list[dict[str, Any]] = []
    population_mismatches: list[dict[str, Any]] = []
    age_total_differences: list[dict[str, Any]] = []

    for code in sorted(basic_codes):
        b = basic[code]
        d = demography[code]
        a = literacy[code]
        r = income.get(code)

        age_0_14 = strict_sum(d, dmap["age_0_14"]["sources"])
        age_15_29 = strict_sum(d, dmap["age_15_29"]["sources"])
        age_30_59 = strict_sum(d, dmap["age_30_59"]["sources"])
        age_60_plus = strict_sum(d, dmap["age_60_plus"]["sources"])

        age_parts = [age_0_14, age_15_29, age_30_59, age_60_plus]
        classified_age_total = (
            sum(value for value in age_parts if value is not None)
            if all(value is not None for value in age_parts)
            else None
        )

        population_15_plus = strict_sum(
            a, lmap["population_15_plus"]["sources"]
        )
        literate_15_plus = strict_sum(
            a, lmap["literate_15_plus"]["sources"]
        )
        literacy_rate = (
            round(100 * literate_15_plus / population_15_plus, 2)
            if population_15_plus not in (None, 0)
            and literate_15_plus is not None
            else None
        )

        population_total = parse_int(
            b.get(variable_map["basic"]["population_total"]["source"])
        )
        population_demography = parse_int(
            d.get(dmap["population_demography"]["source"])
        )

        if (
            population_total is not None
            and population_demography is not None
            and population_total != population_demography
        ):
            population_mismatches.append(
                {
                    "cd_bairro": code,
                    "bairro": b["NM_BAIRRO"],
                    "populacao_total": population_total,
                    "populacao_demografia": population_demography,
                }
            )

        if (
            population_demography is not None
            and classified_age_total is not None
            and population_demography != classified_age_total
        ):
            age_total_differences.append(
                {
                    "cd_bairro": code,
                    "bairro": b["NM_BAIRRO"],
                    "populacao_demografia": population_demography,
                    "populacao_idade_classificada": classified_age_total,
                }
            )

        result.append(
            {
                "cd_bairro": code,
                "bairro": b["NM_BAIRRO"],
                "area_km2": decimal_for_csv(parse_decimal(b.get("AREA_KM2"))),
                "populacao_total": population_total,
                "populacao_demografia": population_demography,
                "idade_0_14": age_0_14,
                "idade_15_29": age_15_29,
                "idade_30_59": age_30_59,
                "idade_60_mais": age_60_plus,
                "populacao_idade_classificada": classified_age_total,
                "populacao_15_mais_alfabetizacao": population_15_plus,
                "alfabetizados_15_mais": literate_15_plus,
                "taxa_alfabetizacao_15_mais_pct": literacy_rate,
                "responsaveis_dpp_ocupados": (
                    parse_int(r.get(imap["responsible_people"]["source"]))
                    if r
                    else None
                ),
                "renda_responsavel_media": (
                    decimal_for_csv(
                        parse_decimal(r.get(imap["responsible_income_mean"]["source"]))
                    )
                    if r
                    else ""
                ),
                "renda_responsavel_mediana": (
                    decimal_for_csv(
                        parse_decimal(r.get(imap["responsible_income_median"]["source"]))
                    )
                    if r
                    else ""
                ),
                "renda_disponivel": bool(r),
            }
        )

    missing_income_codes = sorted(basic_codes - set(income))
    validation = {
        "municipio_ibge": MUNICIPALITY_CODE,
        "bairros": {
            "basic": len(basic),
            "demography": len(demography),
            "literacy": len(literacy),
            "income": len(income),
        },
        "missing_income_count": len(missing_income_codes),
        "missing_income_neighborhoods": [
            {"cd_bairro": code, "bairro": basic[code]["NM_BAIRRO"]}
            for code in missing_income_codes
        ],
        "population_source_mismatch_count": len(population_mismatches),
        "population_source_mismatches": population_mismatches,
        "age_classified_total_difference_count": len(age_total_differences),
        "age_classified_total_differences": age_total_differences,
        "rules": {
            "missing_markers": sorted(MISSING_MARKERS),
            "incomplete_derived_group_becomes_null": True,
            "missing_income_becomes_zero": False,
            "literacy_rate_denominator": "population_15_plus_from_literacy_theme",
        },
    }
    return result, validation


def load_remote_datasets(
    manifest: dict[str, Any],
) -> dict[str, dict[str, dict[str, str]]]:
    by_id = {item["id"]: item for item in manifest["datasets"]}
    output: dict[str, dict[str, dict[str, str]]] = {}

    for key, dataset_id in DATASET_IDS.items():
        source = by_id[dataset_id]
        content = download_bytes(source["url"])
        rows = csv_rows_from_zip(content)
        output[key] = municipality_rows(rows)

    return output


def validate_mapped_columns(
    datasets: dict[str, dict[str, dict[str, str]]],
    variable_map: dict[str, Any],
) -> None:
    validate_required_columns(
        "basic",
        datasets["basic"],
        {"CD_BAIRRO", "NM_BAIRRO", "CD_MUN", "AREA_KM2", "v0001"},
    )

    required_demography = {
        "CD_BAIRRO",
        "NM_BAIRRO",
        variable_map["demography"]["population_demography"]["source"],
    }
    for group in ("age_0_14", "age_15_29", "age_30_59", "age_60_plus"):
        required_demography.update(variable_map["demography"][group]["sources"])
    validate_required_columns(
        "demography",
        datasets["demography"],
        required_demography,
    )

    required_literacy = {"CD_BAIRRO", "NM_BAIRRO"}
    required_literacy.update(
        variable_map["literacy"]["population_15_plus"]["sources"]
    )
    required_literacy.update(
        variable_map["literacy"]["literate_15_plus"]["sources"]
    )
    validate_required_columns(
        "literacy",
        datasets["literacy"],
        required_literacy,
    )

    validate_required_columns(
        "income",
        datasets["income"],
        {
            "CD_BAIRRO",
            "NM_BAIRRO",
            variable_map["income"]["responsible_people"]["source"],
            variable_map["income"]["responsible_income_mean"]["source"],
            variable_map["income"]["responsible_income_median"]["source"],
        },
    )


def write_outputs(
    rows: list[dict[str, Any]],
    validation: dict[str, Any],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "ibge_santos_bairros.csv"
    json_path = output_dir / "ibge_santos_validation.json"

    fieldnames = list(rows[0].keys()) if rows else []
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(validation, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída do snapshot analítico e do relatório de validação.",
    )
    args = parser.parse_args()

    manifest = read_json(SOURCE_MANIFEST)
    variable_map = read_json(VARIABLE_MAP)
    datasets = load_remote_datasets(manifest)
    validate_mapped_columns(datasets, variable_map)

    rows, validation = transform(datasets, variable_map)
    if len(rows) != 70:
        raise EtlError(
            f"Esperados 70 bairros na versão validada do recorte; encontrados {len(rows)}."
        )

    write_outputs(rows, validation, args.output_dir)
    print(
        f"OK: {len(rows)} bairros; "
        f"{validation['missing_income_count']} sem renda publicada; "
        f"saída em {args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
