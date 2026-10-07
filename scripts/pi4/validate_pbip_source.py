#!/usr/bin/env python3
"""Static validation for the versioned PI4 PBIP source project.

This validates PBIP/PBIR JSON files against vendored Microsoft schemas, checks
cross-file references in TMDL, and validates data-bound PBIR visual references.
It does not replace opening the project in Power BI Desktop, which remains the
final semantic processing and rendered-output gate.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[2]
PBIP_ROOT = ROOT / "powerbi" / "pbip"
REPORT = PBIP_ROOT / "BibliotecasConectadasPI4.Report"
MODEL = PBIP_ROOT / "BibliotecasConectadasPI4.SemanticModel"
SCHEMAS = PBIP_ROOT / "schemas"
VISUAL_SCHEMA_URL = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/"
    "definition/visualContainer/2.9.0/schema.json"
)

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

EXPECTED_VISUAL_COUNTS = {
    "ReportSectionVisaoGeral": 4,
    "ReportSectionTerritorio": 3,
    "ReportSectionAcervoTerritorio": 4,
    "ReportSectionCirculacao": 4,
    "ReportSectionMetodologia": 2,
}

ALLOWED_VISUAL_TYPES = {
    "cardVisual",
    "clusteredBarChart",
    "lineChart",
    "tableEx",
    "slicer",
    "azureMap",
}

ROLE_REQUIREMENTS = {
    "cardVisual": {"Data"},
    "clusteredBarChart": {"Category", "Y"},
    "lineChart": {"Category", "Y"},
    "tableEx": {"Values"},
    "slicer": {"Values"},
    "azureMap": {"Category"},
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


def unquote_tmdl_name(raw: str) -> str:
    value = raw.strip()
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    return value


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
        refs.add(unquote_tmdl_name(stripped[len("ref table "):]))
    return refs


def parse_table_objects(text: str) -> tuple[str, set[str], set[str]]:
    table_match = re.search(r"(?m)^table\s+(.+?)\s*$", text)
    if not table_match:
        raise ValidationError("Arquivo TMDL sem declaração table.")

    table = unquote_tmdl_name(table_match.group(1))

    columns = {
        unquote_tmdl_name(match.group(1))
        for match in re.finditer(r"(?m)^\s*column\s+(.+?)\s*$", text)
    }
    measures = {
        unquote_tmdl_name(match.group(1))
        for match in re.finditer(r"(?m)^\s*measure\s+(.+?)\s*=", text)
    }
    return table, columns, measures


def load_model_objects() -> dict[str, dict[str, set[str]]]:
    tables_dir = MODEL / "definition" / "tables"
    result: dict[str, dict[str, set[str]]] = {}
    for path in tables_dir.glob("*.tmdl"):
        table, columns, measures = parse_table_objects(
            path.read_text(encoding="utf-8")
        )
        if table in result:
            raise ValidationError(f"Tabela TMDL duplicada: {table}")
        result[table] = {"columns": columns, "measures": measures}
    return result


def validate_tmdl() -> dict[str, dict[str, set[str]]]:
    model_text = (MODEL / "definition" / "model.tmdl").read_text(encoding="utf-8")
    refs = parse_model_refs(model_text)
    if refs != EXPECTED_TABLES:
        raise ValidationError(
            f"Refs de tabelas divergentes. Esperado={sorted(EXPECTED_TABLES)}; "
            f"encontrado={sorted(refs)}"
        )

    model_objects = load_model_objects()
    if set(model_objects) != EXPECTED_TABLES:
        raise ValidationError(
            f"Arquivos de tabela divergentes. Esperado={sorted(EXPECTED_TABLES)}; "
            f"encontrado={sorted(model_objects)}"
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
        table = unquote_tmdl_name(match.group("table"))
        column = unquote_tmdl_name(match.group("column"))

        if table not in model_objects:
            raise ValidationError(f"Relacionamento aponta para tabela ausente: {table}")
        if column not in model_objects[table]["columns"]:
            raise ValidationError(
                f"Relacionamento aponta para coluna ausente: {table}.{column}"
            )

    tables_dir = MODEL / "definition" / "tables"
    for path in tables_dir.glob("*.tmdl"):
        text = path.read_text(encoding="utf-8")
        if "gestor/analytics/powerbi/" not in text:
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

    return model_objects


def iter_field_references(value: Any):
    if isinstance(value, dict):
        column = value.get("Column")
        if isinstance(column, dict):
            source = (
                column.get("Expression", {})
                .get("SourceRef", {})
                .get("Entity")
            )
            prop = column.get("Property")
            if source and prop:
                yield "column", str(source), str(prop)

        measure = value.get("Measure")
        if isinstance(measure, dict):
            source = (
                measure.get("Expression", {})
                .get("SourceRef", {})
                .get("Entity")
            )
            prop = measure.get("Property")
            if source and prop:
                yield "measure", str(source), str(prop)

        for child in value.values():
            yield from iter_field_references(child)

    elif isinstance(value, list):
        for child in value:
            yield from iter_field_references(child)


def validate_visuals(model_objects: dict[str, dict[str, set[str]]]) -> None:
    pages_root = REPORT / "definition" / "pages"
    seen_names: dict[str, set[str]] = {page: set() for page in EXPECTED_PAGES}
    total = 0

    for page, expected_count in EXPECTED_VISUAL_COUNTS.items():
        visuals_root = pages_root / page / "visuals"
        visual_files = sorted(visuals_root.glob("*/visual.json"))
        if len(visual_files) != expected_count:
            raise ValidationError(
                f"{page}: esperados {expected_count} visuais; "
                f"encontrados {len(visual_files)}."
            )

        for path in visual_files:
            total += 1
            data = read_json(path)

            if data.get("$schema") != VISUAL_SCHEMA_URL:
                raise ValidationError(
                    f"{path}: schema visual inesperado: {data.get('$schema')}"
                )

            name = str(data.get("name") or "")
            if name != path.parent.name:
                raise ValidationError(
                    f"{path}: name '{name}' diverge do diretório '{path.parent.name}'."
                )
            if name in seen_names[page]:
                raise ValidationError(f"{page}: visual duplicado {name}.")
            seen_names[page].add(name)

            pos = data.get("position") or {}
            for key in ("x", "y", "width", "height"):
                if not isinstance(pos.get(key), (int, float)):
                    raise ValidationError(f"{path}: position.{key} inválido.")
            if pos["x"] < 0 or pos["y"] < 0:
                raise ValidationError(f"{path}: visual fora do canvas.")
            if pos["x"] + pos["width"] > 1280:
                raise ValidationError(f"{path}: visual ultrapassa largura do canvas.")
            if pos["y"] + pos["height"] > 720:
                raise ValidationError(f"{path}: visual ultrapassa altura do canvas.")

            visual = data.get("visual")
            if not isinstance(visual, dict):
                raise ValidationError(f"{path}: bloco visual ausente.")

            visual_type = visual.get("visualType")
            if visual_type not in ALLOWED_VISUAL_TYPES:
                raise ValidationError(
                    f"{path}: visualType não permitido/esperado: {visual_type}"
                )

            query_state = (
                visual.get("query", {})
                .get("queryState", {})
            )
            required_roles = ROLE_REQUIREMENTS[visual_type]
            missing_roles = required_roles - set(query_state)
            if missing_roles:
                raise ValidationError(
                    f"{path}: papéis obrigatórios ausentes: {sorted(missing_roles)}"
                )

            for role in required_roles:
                projections = (query_state.get(role) or {}).get("projections") or []
                if not projections:
                    raise ValidationError(
                        f"{path}: role {role} não possui projeções."
                    )

            if visual_type == "slicer":
                mode = (
                    visual.get("objects", {})
                    .get("data", [{}])[0]
                    .get("properties", {})
                    .get("mode", {})
                    .get("expr", {})
                    .get("Literal", {})
                    .get("Value")
                )
                if mode != "'Dropdown'":
                    raise ValidationError(
                        f"{path}: slicer esperado como Dropdown; encontrado {mode!r}."
                    )

            for kind, table, prop in iter_field_references(visual):
                if table not in model_objects:
                    raise ValidationError(
                        f"{path}: campo aponta para tabela ausente {table}."
                    )
                bucket = "columns" if kind == "column" else "measures"
                if prop not in model_objects[table][bucket]:
                    raise ValidationError(
                        f"{path}: {kind} ausente no modelo: {table}.{prop}"
                    )

    if total != sum(EXPECTED_VISUAL_COUNTS.values()):
        raise ValidationError(f"Total visual inesperado: {total}.")


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
    model_objects = validate_tmdl()
    validate_visuals(model_objects)
    validate_no_credentials()
    total_visuals = sum(EXPECTED_VISUAL_COUNTS.values())
    print(
        "OK: PBIP/PBIR JSON validado com schemas Microsoft; "
        f"5 páginas; 8 tabelas; 7 relacionamentos; {total_visuals} visuais "
        "com referências de modelo conferidas; segurança estática aprovada."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
