from django.db import migrations
from django.db.models import Q


def clear_unverified_mario_faria_coordinates(apps, schema_editor):
    Unidade = apps.get_model("gestor", "Unidade")
    Unidade.objects.filter(
        Q(nome__icontains="Mário Faria") | Q(nome__icontains="Mario Faria")
    ).update(
        latitude=None,
        longitude=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("gestor", "0016_unidade_territorio_ibge"),
    ]

    operations = [
        migrations.RunPython(
            clear_unverified_mario_faria_coordinates,
            migrations.RunPython.noop,
        ),
    ]
