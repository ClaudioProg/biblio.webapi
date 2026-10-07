from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.db.models import Count, Max, Min, Sum
from django.db.models.functions import TruncMonth

from gestor.domain.entities.emprestimo import Emprestimo
from gestor.domain.entities.livro_unidade import LivroUnidade
from gestor.domain.entities.unidade import Unidade
from gestor.infrastructure.territory_service import (
    load_territory_snapshot,
    neighborhood_name_by_code,
)


def _month_key(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.replace(day=1).isoformat()
    raise TypeError(f"Tipo de mês inesperado: {type(value)!r}")


def _decimal_or_none(value):
    return float(value) if value is not None else None


def build_powerbi_dataset() -> dict[str, Any]:
    territory_rows, validation = load_territory_snapshot()

    dim_bairro = list(territory_rows)

    dim_unidade = [
        {
            "unidade_id": row["id"],
            "unidade": row["nome"],
            "endereco": row["endereco"],
            "ibge_bairro_codigo": row["ibge_bairro_codigo"],
            "ibge_bairro_nome": neighborhood_name_by_code(
                row["ibge_bairro_codigo"]
            ),
            "latitude": _decimal_or_none(row["latitude"]),
            "longitude": _decimal_or_none(row["longitude"]),
        }
        for row in Unidade.objects.all()
        .order_by("id")
        .values(
            "id",
            "nome",
            "endereco",
            "ibge_bairro_codigo",
            "latitude",
            "longitude",
        )
    ]

    open_by_acervo_group = {
        (
            row["unidade_id"],
            row["livro__genero__nome"] or "Não informado",
            row["livro__tipo_obra__nome"] or "Não informado",
        ): row["emprestimos_abertos"]
        for row in Emprestimo.objects.filter(
            status=Emprestimo.STATUS_ABERTO
        )
        .values(
            "unidade_id",
            "livro__genero__nome",
            "livro__tipo_obra__nome",
        )
        .annotate(emprestimos_abertos=Count("id"))
    }

    fato_acervo = []
    for row in (
        LivroUnidade.objects.values(
            "unidade_id",
            "unidade__ibge_bairro_codigo",
            "livro__genero__nome",
            "livro__tipo_obra__nome",
        )
        .annotate(
            titulos=Count("livro_id", distinct=True),
            exemplares=Sum("exemplares"),
        )
        .order_by(
            "unidade_id",
            "livro__genero__nome",
            "livro__tipo_obra__nome",
        )
    ):
        genero = row["livro__genero__nome"] or "Não informado"
        tipo_obra = row["livro__tipo_obra__nome"] or "Não informado"
        exemplares = int(row["exemplares"] or 0)
        abertos = int(
            open_by_acervo_group.get(
                (row["unidade_id"], genero, tipo_obra),
                0,
            )
            or 0
        )
        fato_acervo.append(
            {
                "unidade_id": row["unidade_id"],
                "ibge_bairro_codigo": row["unidade__ibge_bairro_codigo"],
                "genero": genero,
                "tipo_obra": tipo_obra,
                "titulos": row["titulos"],
                "exemplares": exemplares,
                "emprestimos_abertos": abertos,
                "exemplares_disponiveis": max(0, exemplares - abertos),
            }
        )

    fato_circulacao_mensal = [
        {
            "mes": _month_key(row["mes"]),
            "unidade_id": row["unidade_id"],
            "ibge_bairro_codigo": row["unidade__ibge_bairro_codigo"],
            "genero": row["livro__genero__nome"] or "Não informado",
            "tipo_obra": row["livro__tipo_obra__nome"] or "Não informado",
            "emprestimos_iniciados": row["emprestimos_iniciados"],
        }
        for row in Emprestimo.objects.annotate(
            mes=TruncMonth("data_emprestimo")
        )
        .values(
            "mes",
            "unidade_id",
            "unidade__ibge_bairro_codigo",
            "livro__genero__nome",
            "livro__tipo_obra__nome",
        )
        .annotate(emprestimos_iniciados=Count("id"))
        .order_by("mes", "unidade_id")
        if row["mes"] is not None
    ]

    fato_devolucoes_mensal = [
        {
            "mes": _month_key(row["mes"]),
            "unidade_id": row["unidade_id"],
            "ibge_bairro_codigo": row["unidade__ibge_bairro_codigo"],
            "genero": row["livro__genero__nome"] or "Não informado",
            "tipo_obra": row["livro__tipo_obra__nome"] or "Não informado",
            "devolucoes": row["devolucoes"],
        }
        for row in Emprestimo.objects.filter(
            data_devolucao__isnull=False
        )
        .annotate(mes=TruncMonth("data_devolucao"))
        .values(
            "mes",
            "unidade_id",
            "unidade__ibge_bairro_codigo",
            "livro__genero__nome",
            "livro__tipo_obra__nome",
        )
        .annotate(devolucoes=Count("id"))
        .order_by("mes", "unidade_id")
        if row["mes"] is not None
    ]

    open_counts = {
        (row["unidade_id"], row["livro_id"]): row["abertos"]
        for row in Emprestimo.objects.filter(
            status=Emprestimo.STATUS_ABERTO
        )
        .values("unidade_id", "livro_id")
        .annotate(abertos=Count("id"))
    }

    stock = {
        (row["unidade_id"], row["livro_id"]): row["exemplares"]
        for row in LivroUnidade.objects.values(
            "unidade_id",
            "livro_id",
            "exemplares",
        )
    }

    fato_titulos = []
    for row in (
        Emprestimo.objects.values(
            "unidade_id",
            "unidade__ibge_bairro_codigo",
            "livro_id",
            "livro__titulo",
            "livro__autor",
            "livro__isbn",
            "livro__genero__nome",
            "livro__tipo_obra__nome",
        )
        .annotate(emprestimos_total=Count("id"))
        .order_by("-emprestimos_total", "livro__titulo")
    ):
        key = (row["unidade_id"], row["livro_id"])
        exemplares = int(stock.get(key, 0) or 0)
        abertos = int(open_counts.get(key, 0) or 0)
        fato_titulos.append(
            {
                "unidade_id": row["unidade_id"],
                "ibge_bairro_codigo": row["unidade__ibge_bairro_codigo"],
                "livro_id": row["livro_id"],
                "titulo": row["livro__titulo"],
                "autor": row["livro__autor"],
                "isbn": row["livro__isbn"],
                "genero": row["livro__genero__nome"] or "Não informado",
                "tipo_obra": row["livro__tipo_obra__nome"] or "Não informado",
                "emprestimos_total": row["emprestimos_total"],
                "emprestimos_abertos": abertos,
                "exemplares_atuais": exemplares,
                "exemplares_disponiveis": max(0, exemplares - abertos),
            }
        )

    period = Emprestimo.objects.aggregate(
        primeiro_emprestimo=Min("data_emprestimo"),
        ultimo_emprestimo=Max("data_emprestimo"),
        ultima_devolucao=Max("data_devolucao"),
    )

    return {
        "meta": {
            "dataset": "Bibliotecas Conectadas — PI4 — Power BI",
            "municipio": "Santos",
            "codigo_municipio_ibge": "3548500",
            "nivel_territorial": "bairro",
            "contem_dados_pessoais": False,
            "observacao": (
                "Dataset analítico agregado. Não contém nome, e-mail, documento "
                "ou outro identificador de leitores."
            ),
        },
        "periodo": {
            key: value.isoformat() if value else None
            for key, value in period.items()
        },
        "qualidade_ibge": {
            "bairros_total": validation["bairros"]["basic"],
            "bairros_com_renda": validation["bairros"]["income"],
            "bairros_sem_renda": validation["missing_income_count"],
            "diferencas_total_basico_demografia": validation[
                "population_source_mismatch_count"
            ],
            "diferencas_total_demografia_faixas_etarias": validation[
                "age_classified_total_difference_count"
            ],
        },
        "dim_bairro": dim_bairro,
        "dim_unidade": dim_unidade,
        "fato_acervo": fato_acervo,
        "fato_circulacao_mensal": fato_circulacao_mensal,
        "fato_devolucoes_mensal": fato_devolucoes_mensal,
        "fato_titulos": fato_titulos,
    }
