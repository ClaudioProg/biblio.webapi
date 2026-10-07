#!/usr/bin/env python3
"""Static validation for the versioned PI4 PBIP source project.

This validates the PBIP/PBIR JSON files against vendored Microsoft schemas and
checks cross-file references in the TMDL source. It does not replace opening
the project in Power BI Desktop, which remains the final semantic/render check.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[2]
PBIP_ROOT = ROOT / "powerbi" / "pbip"
REPORT = PBIP_ROOT / "BibliotecasConectadasPI4.Report"
MODEL = PBIP_ROOT / "BibliotecasConectadasPI4.SemanticModel"
SCHEMAS = PBIP_ROOT / "schemas"

JSON_CHECKS = [
    (
        PBIP_ROOT / "BibliotecasConectadasPI4.pbip",
        SCHEMAS / "pbip-1.0.0.json",
    ),
    (
        REPORT / "definition.pbir",
        SCHEMAS / "report-definitionProperties-2.0.0.json",
    ),
    (
        REPORT / "definition" / "version.json",
        SCHEMAS / "report-versionMetadata-1.0.0.json",
    ),
    (
        REPORT / "definition" / "report.json",
        SCHEMAS / "report-3.3.0.json",
    ),
    (
        REPORT / "definition" / "pages" / "pages.json",
        SCHEMAS / "pagesMetadata-1.1.0.json",
    ),
    (
        MODEL / "definition.pbism",
        SCHEMAS / "semanticModel-definitionProperties-1.0.0.json",
    ),
]

EXPECTED_TABLES = {
    "Bairros",
    "Bibliotecas",
    "Acervo",
    "Circulação Mensal",
    "Devoluções Mensais",
    "Títulos",
    "Calendário",
    "Qualidade IBGE",
}

EXPECTED_PAGES = {
    "ReportSectionVisaoGeral",
    "ReportSectionTerritorio",
    "ReportSectionAcervoTerritorio",
    "ReportSectionCirculacao",
    "ReportSectionMetodologia",
}

SECRET_PATTERNS = [
    re.compile(r"password\s*[:=]", re.IGNORECASE),
    re.compile(r"senha\s*[:=]", re.IGNORECASE),
    re.compile(r"authorization\s*[:=]\s*[\"']?(?:basic|token)", re.IGNORECASE),
]


class ValidationError(RuntimeError):
    pass


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_json_files() -> None:
    for data_path, schema_path in JSON_CHECKS:
        data = read_json(data_path)
        schema = read_json(schema_path)
        validator = Draft7Validator(schema)
        errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        if errors:
            details = "; ".join(
                f"{data_path.name}:{'/'.join(map(str, error.path))}: {error.message}"
                for error in errors
            )
            raise ValidationError(details)

    page_schema = read_json(SCHEMAS / "page-2.1.0.json")
    page_validator = Draft7Validator(page_schema)
    pages_root = REPORT / "definition" / "pages"
    for page_name in EXPECTED_PAGES:
        page_path = pages_root / page_name / "page.json"
        if not page_path.exists():
            raise ValidationError(f"Página ausente: {page_name}")
        errors = sorted(
            page_validator.iter_errors(read_json(page_path)),
            key=lambda e: list(e.path),
        )
        if errors:
            raise ValidationError(
                f"{page_path}: "
                + "; ".join(error.message for error in errors)
            )


def parse_model_refs(model_text: str) -> set[str]:
    refs = set()
    for line in model_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("ref table "):
            continue
        name = stripped[len("ref table "):].strip()
        if name.startswith("'") and name.endswith("'"):
            name = name[1:-1].replace("''", "'")
        refs.add(name)
    return refs


def parse_table_columns(text: str) -> tuple[str, set[str]]:
    table_match = re.search(r"(?m)^table\s+(.+?)\s*$", text)
    if not table_match:
        raise ValidationError("Arquivo TMDL sem declaração table.")

    raw_table = table_match.group(1).strip()
    table = (
        raw_table[1:-1].replace("''", "'")
        if raw_table.startswith("'") and raw_table.endswith("'")
        else raw_table
    )

    columns = set()
    for match in re.finditer(r"(?m)^\s*column\s+(.+?)\s*$", text):
        raw = match.group(1).strip()
        name = (
            raw[1:-1].replace("''", "'")
            if raw.startswith("'") and raw.endswith("'")
            else raw
        )
        columns.add(name)
    return table, columns


def validate_tmdl() -> None:
    model_text = (MODEL / "definition" / "model.tmdl").read_text(encoding="utf-8")
    refs = parse_model_refs(model_text)
    if refs != EXPECTED_TABLES:
        raise ValidationError(
            f"Refs de tabelas divergentes. Esperado={sorted(EXPECTED_TABLES)}; "
            f"encontrado={sorted(refs)}"
        )

    tables_dir = MODEL / "definition" / "tables"
    table_columns = {}
    for path in tables_dir.glob("*.tmdl"):
        table, columns = parse_table_columns(path.read_text(encoding="utf-8"))
        if table in table_columns:
            raise ValidationError(f"Tabela TMDL duplicada: {table}")
        table_columns[table] = columns

    if set(table_columns) != EXPECTED_TABLES:
        raise ValidationError(
            f"Arquivos de tabela divergentes. Esperado={sorted(EXPECTED_TABLES)}; "
            f"encontrado={sorted(table_columns)}"
        )

    relationships = (
        MODEL / "definition" / "relationships.tmdl"
    ).read_text(encoding="utf-8")

    pattern = re.compile(
        r"(?m)^\s*(?:fromColumn|toColumn):\s+"
        r"(?P<table>'[^']+'|[^.]+)\.(?P<column>'[^']+'|[^\r\n]+)$"
    )
    matches = list(pattern.finditer(relationships))
    if len(matches) != 14:
        raise ValidationError(
            f"Esperadas 14 referências de coluna nos relacionamentos; "
            f"encontradas {len(matches)}."
        )

    for match in matches:
        table = match.group("table").strip()
        column = match.group("column").strip()
        if table.startswith("'") and table.endswith("'"):
            table = table[1:-1].replace("''", "'")
        if column.startswith("'") and column.endswith("'"):
            column = column[1:-1].replace("''", "'")

        if table not in table_columns:
            raise ValidationError(f"Relacionamento aponta para tabela ausente: {table}")
        if column not in table_columns[table]:
            raise ValidationError(
                f"Relacionamento aponta para coluna ausente: {table}.{column}"
            )

    for path in tables_dir.glob("*.tmdl"):
        text = path.read_text(encoding="utf-8")
        if "gestor/analytics/powerbi/" not in text:
            if path.name not in {"Calendário.tmdl"}:
                raise ValidationError(
                    f"{path.name} não referencia o endpoint analítico esperado."
                )
        if "http://" in text:
            raise ValidationError(f"Fonte HTTP não segura encontrada em {path.name}.")
        if re.search(r"\b(?:email|documento|usuario_nome|telefone)\b", text, re.I):
            raise ValidationError(
                f"Possível campo pessoal indevido no modelo: {path.name}"
            )
        if re.search(r"[A-Za-zÀ-ÿ]+\['[^']+'\]", text):
            raise ValidationError(
                f"Referência DAX potencialmente inválida no formato Table['Column']: {path.name}"
            )


def validate_report_links() -> None:
    pbip = read_json(PBIP_ROOT / "BibliotecasConectadasPI4.pbip")
    report_path = pbip["artifacts"][0]["report"]["path"]
    if report_path != "BibliotecasConectadasPI4.Report":
        raise ValidationError(f"Atalho PBIP aponta para caminho inesperado: {report_path}")

    pbir = read_json(REPORT / "definition.pbir")
    model_path = pbir["datasetReference"]["byPath"]["path"]
    if model_path != "../BibliotecasConectadasPI4.SemanticModel":
        raise ValidationError(f"definition.pbir aponta para modelo inesperado: {model_path}")

    pages = read_json(REPORT / "definition" / "pages" / "pages.json")
    order = pages.get("pageOrder", [])
    if set(order) != EXPECTED_PAGES or len(order) != len(EXPECTED_PAGES):
        raise ValidationError("pageOrder não contém exatamente as cinco páginas planejadas.")
    if pages.get("activePageName") != "ReportSectionVisaoGeral":
        raise ValidationError("Página inicial do relatório não é Visão Geral.")


def validate_no_credentials() -> None:
    for path in PBIP_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".tmdl", ".pbip", ".pbir"}:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                raise ValidationError(
                    f"Possível credencial embutida em {path.relative_to(PBIP_ROOT)}"
                )


def main() -> int:
    validate_json_files()
    validate_report_links()
    validate_tmdl()
    validate_no_credentials()
    print(
        "OK: PBIP/PBIR JSON validado com schemas Microsoft; "
        "5 páginas; 8 tabelas; relacionamentos e segurança estática conferidos."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
