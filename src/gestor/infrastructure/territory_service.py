from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.conf import settings

DATA_DIR = Path(settings.BASE_DIR) / "data" / "pi4"
TERRITORY_CSV = DATA_DIR / "ibge_santos_bairros.csv"
VALIDATION_JSON = DATA_DIR / "ibge_santos_validation.json"

INTEGER_FIELDS = {
    "populacao_total",
    "populacao_demografia",
    "idade_0_14",
    "idade_15_29",
    "idade_30_59",
    "idade_60_mais",
    "populacao_idade_classificada",
    "populacao_15_mais_alfabetizacao",
    "alfabetizados_15_mais",
    "responsaveis_dpp_ocupados",
}

FLOAT_FIELDS = {
    "area_km2",
    "taxa_alfabetizacao_15_mais_pct",
    "renda_responsavel_media",
    "renda_responsavel_mediana",
}


def _number_or_none(value: str, *, integer: bool) -> int | float | None:
    text = str(value or "").strip()
    if not text:
        return None
    return int(text) if integer else float(text)


def _bool_value(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "sim"}


def _normalize_row(row: dict[str, str]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if key in INTEGER_FIELDS:
            normalized[key] = _number_or_none(value, integer=True)
        elif key in FLOAT_FIELDS:
            normalized[key] = _number_or_none(value, integer=False)
        elif key == "renda_disponivel":
            normalized[key] = _bool_value(value)
        else:
            normalized[key] = value
    return normalized


@lru_cache(maxsize=1)
def load_territory_snapshot() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not TERRITORY_CSV.exists():
        raise FileNotFoundError(
            f"Snapshot territorial não encontrado: {TERRITORY_CSV}"
        )
    if not VALIDATION_JSON.exists():
        raise FileNotFoundError(
            f"Relatório de validação não encontrado: {VALIDATION_JSON}"
        )

    with TERRITORY_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [_normalize_row(row) for row in csv.DictReader(handle)]

    with VALIDATION_JSON.open("r", encoding="utf-8") as handle:
        validation = json.load(handle)

    return rows, validation


def neighborhood_by_code(code: str) -> dict[str, Any] | None:
    normalized = str(code or "").strip()
    if not normalized:
        return None

    rows, _validation = load_territory_snapshot()
    return next(
        (row for row in rows if row["cd_bairro"] == normalized),
        None,
    )


def neighborhood_name_by_code(code: str) -> str | None:
    row = neighborhood_by_code(code)
    return str(row["bairro"]) if row else None


def is_valid_neighborhood_code(code: str) -> bool:
    return neighborhood_by_code(code) is not None


def territory_payload(
    *,
    neighborhood_code: str = "",
    neighborhood_name: str = "",
) -> dict[str, Any]:
    rows, validation = load_territory_snapshot()

    filtered = rows
    if neighborhood_code:
        filtered = [
            row
            for row in filtered
            if row["cd_bairro"] == neighborhood_code
        ]

    if neighborhood_name:
        query = neighborhood_name.casefold()
        filtered = [
            row
            for row in filtered
            if query in str(row["bairro"]).casefold()
        ]

    with_income = sum(1 for row in rows if row["renda_disponivel"])
    with_literacy = sum(
        1
        for row in rows
        if row["taxa_alfabetizacao_15_mais_pct"] is not None
    )
    with_age = sum(
        1
        for row in rows
        if row["populacao_idade_classificada"] is not None
    )

    return {
        "meta": {
            "fonte": "IBGE — Censo Demográfico 2022",
            "municipio": "Santos",
            "uf": "SP",
            "codigo_municipio_ibge": "3548500",
            "nivel_territorial": "bairro",
            "gerado_de_fontes_oficiais_em": validation.get(
                "generated_from_official_sources_on"
            ),
            "contem_dados_pessoais": False,
            "observacao": (
                "Os dados caracterizam o território e não constituem, isoladamente, "
                "evidência de preferência ou demanda literária."
            ),
        },
        "cobertura": {
            "bairros_total": len(rows),
            "bairros_com_demografia": validation["bairros"]["demography"],
            "bairros_com_alfabetizacao": validation["bairros"]["literacy"],
            "bairros_com_renda": with_income,
            "bairros_com_faixas_etarias_completas": with_age,
            "bairros_com_taxa_alfabetizacao": with_literacy,
            "bairros_sem_renda": validation["missing_income_count"],
        },
        "validacao": {
            "diferencas_total_basico_demografia": validation[
                "population_source_mismatch_count"
            ],
            "diferencas_total_demografia_faixas_etarias": validation[
                "age_classified_total_difference_count"
            ],
            "renda_ausente_eh_zero": False,
        },
        "bairros": filtered,
    }
