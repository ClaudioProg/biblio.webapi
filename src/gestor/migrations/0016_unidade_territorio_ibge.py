from django.db import migrations, models
from django.db.models import Q


MARIO_FARIA_BAIRRO = "3548500005"
MARIO_FARIA_LATITUDE = "-23.979587"
MARIO_FARIA_LONGITUDE = "-46.314403"


def backfill_mario_faria(apps, schema_editor):
    Unidade = apps.get_model("gestor", "Unidade")
    Unidade.objects.filter(
        Q(nome__icontains="Mário Faria") | Q(nome__icontains="Mario Faria")
    ).update(
        ibge_bairro_codigo=MARIO_FARIA_BAIRRO,
        latitude=MARIO_FARIA_LATITUDE,
        longitude=MARIO_FARIA_LONGITUDE,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("gestor", "0015_bootstrap_admin_from_env"),
    ]

    operations = [
        migrations.AddField(
            model_name="unidade",
            name="ibge_bairro_codigo",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="unidade",
            name="latitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="unidade",
            name="longitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
            ),
        ),
        migrations.RunPython(backfill_mario_faria, migrations.RunPython.noop),
    ]
