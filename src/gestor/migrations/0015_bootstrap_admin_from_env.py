import os

from django.contrib.auth.hashers import make_password
from django.db import migrations


def bootstrap_admin(apps, schema_editor):
    username = os.getenv("BIBLIO_ADMIN_USERNAME", "").strip()
    password = os.getenv("BIBLIO_ADMIN_PASSWORD", "")
    email = os.getenv("BIBLIO_ADMIN_EMAIL", "").strip()

    if not username or not password:
        return

    User = apps.get_model("auth", "User")
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={"email": email},
    )

    user.email = email or user.email
    user.is_active = True
    user.is_staff = True
    user.is_superuser = True
    user.password = make_password(password)
    user.save(
        update_fields=[
            "email",
            "is_active",
            "is_staff",
            "is_superuser",
            "password",
        ]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("gestor", "0014_protect_emprestimo_history"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(bootstrap_admin, migrations.RunPython.noop),
    ]
