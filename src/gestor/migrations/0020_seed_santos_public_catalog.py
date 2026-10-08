import json
import random
from datetime import date
from pathlib import Path

from django.db import migrations


SEED_FILE = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "seeds"
    / "santos_100_books.json"
)

PUBLIC_UNITS = [
    {
        "nome": "Biblioteca Alberto Sousa",
        "endereco": "Praça José Bonifácio, 58 – Centro, Santos/SP",
        "telefone": "(13) 3221-2435",
        "email": "",
        "site": "https://www.santos.sp.gov.br/?q=servico%2Fbibliotecas-municipais",
        "ibge_bairro_codigo": "3548500017",
    },
    {
        "nome": "Biblioteca Municipal Mário Faria",
        "endereco": "Av. Bartolomeu de Gusmão, s/nº – Aparecida (Posto 6), Santos/SP",
        "telefone": "(13) 3231-8713",
        "email": "",
        "site": "https://www.santos.sp.gov.br/?q=local%2Fbiblioteca-municipal-mario-faria",
        "ibge_bairro_codigo": "3548500005",
    },
    {
        "nome": "Biblioteca Dr. Silvério Fontes",
        "endereco": "Centro Cultural da Zona Noroeste – Av. Afonso Schmidt, s/nº – Areia Branca, Santos/SP",
        "telefone": "",
        "email": "",
        "site": "https://www.santos.sp.gov.br/?q=local%2Fbiblioteca-dr-silverio-fontes",
        "ibge_bairro_codigo": "3548500028",
    },
    {
        "nome": "Biblioteca Plínio Marcos",
        "endereco": "Praça das Palmeiras, s/nº – Caruara, Santos/SP",
        "telefone": "(13) 3219-6019",
        "email": "",
        "site": "https://www.santos.sp.gov.br/?q=local%2Fbiblioteca-plinio-marcos",
        "ibge_bairro_codigo": "3548500061",
    },
    {
        "nome": "Biblioteca do CEU das Artes",
        "endereco": "Praça da Paz Universal, s/nº – Castelo, Santos/SP",
        "telefone": "",
        "email": "",
        "site": "https://www.santos.sp.gov.br/?q=servico%2Fbibliotecas-municipais",
        "ibge_bairro_codigo": "3548500029",
    },
    {
        "nome": "Gibiteca Marcel Rodrigues Paes",
        "endereco": "Av. Bartolomeu de Gusmão, s/nº – Posto 5 – Boqueirão, Santos/SP",
        "telefone": "(13) 3288-1300",
        "email": "",
        "site": "https://www.santos.sp.gov.br/?q=local%2Fgibiteca-marcel-rodrigues-paes",
        "ibge_bairro_codigo": "3548500003",
    },
]


def seed_santos_public_catalog(apps, schema_editor):
    Unidade = apps.get_model("gestor", "Unidade")
    Livro = apps.get_model("gestor", "Livro")
    LivroUnidade = apps.get_model("gestor", "LivroUnidade")
    Genero = apps.get_model("gestor", "Genero")
    TipoObra = apps.get_model("gestor", "TipoObra")
    Emprestimo = apps.get_model("gestor", "Emprestimo")

    # Remove apenas artefatos claramente identificados como teste.
    test_units = Unidade.objects.filter(nome__icontains="teste")
    Emprestimo.objects.filter(unidade__in=test_units).delete()
    LivroUnidade.objects.filter(unidade__in=test_units).delete()
    test_units.delete()

    Livro.objects.filter(
        isbn__in=["09-04346", "978850000001"]
    ).delete()

    real_units = []
    for payload in PUBLIC_UNITS:
        unit, _ = Unidade.objects.update_or_create(
            nome=payload["nome"],
            defaults=payload,
        )
        real_units.append(unit)

    livro_tipo, _ = TipoObra.objects.get_or_create(nome="Livro")

    with SEED_FILE.open("r", encoding="utf-8") as handle:
        books = json.load(handle)

    if len(books) != 100:
        raise RuntimeError(
            f"Seed de livros deve conter exatamente 100 itens; encontrado {len(books)}."
        )

    genre_cache = {}
    rng = random.Random(20261008)

    for item in books:
        genre_name = item["genero"]
        genero = genre_cache.get(genre_name)
        if genero is None:
            genero, _ = Genero.objects.get_or_create(nome=genre_name)
            genre_cache[genre_name] = genero

        year = item.get("ano")
        publication_date = (
            date(int(year), 1, 1)
            if isinstance(year, int) and 1 <= year <= 9999
            else None
        )

        livro, _ = Livro.objects.update_or_create(
            isbn=item["isbn"],
            defaults={
                "titulo": item["titulo"],
                "autor": item["autor"],
                "genero": genero,
                "tipo_obra": livro_tipo,
                "editora": item.get("editora") or "",
                "data_publicacao": publication_date,
                "paginas": None,
                "capa": item.get("capa") or "",
                "idioma": item.get("idioma") or "",
            },
        )

        unit_count = rng.randint(2, 4)
        selected = rng.sample(real_units, unit_count)
        selected_ids = [unit.id for unit in selected]

        LivroUnidade.objects.filter(livro=livro).exclude(
            unidade_id__in=selected_ids
        ).delete()

        for unit in selected:
            LivroUnidade.objects.update_or_create(
                livro=livro,
                unidade=unit,
                defaults={"exemplares": rng.randint(1, 6)},
            )


class Migration(migrations.Migration):

    dependencies = [
        ("gestor", "0019_ensure_claudio_admin_from_env"),
    ]

    operations = [
        migrations.RunPython(
            seed_santos_public_catalog,
            migrations.RunPython.noop,
        ),
    ]
