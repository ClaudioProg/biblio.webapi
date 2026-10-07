from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("gestor", "0013_emprestimo_unidade"),
    ]

    operations = [
        migrations.AlterField(
            model_name="emprestimo",
            name="livro",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="gestor.livro",
            ),
        ),
        migrations.AlterField(
            model_name="emprestimo",
            name="unidade",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="gestor.unidade",
            ),
        ),
        migrations.AlterField(
            model_name="emprestimo",
            name="usuario",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="gestor.usuario",
            ),
        ),
    ]
