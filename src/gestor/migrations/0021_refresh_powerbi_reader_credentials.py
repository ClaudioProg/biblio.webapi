import os

from django.contrib.auth.hashers import make_password
from django.db import migrations


GROUP_NAME = "powerbi_reader"


def refresh_powerbi_reader(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")

    username = os.getenv("BIBLIO_POWERBI_USERNAME", "").strip()
    password = os.getenv("BIBLIO_POWERBI_PASSWORD", "")
    email = os.getenv("BIBLIO_POWERBI_EMAIL", "").strip()

    if not username or not password:
        return

    group, _ = Group.objects.get_or_create(name=GROUP_NAME)

    user, _ = User.objects.get_or_create(
        username=username,
        defaults={
            "email": email,
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
        },
    )

    user.email = email or user.email
    user.is_active = True
    user.is_staff = False
    user.is_superuser = False
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
    user.groups.add(group)


class Migration(migrations.Migration):

    dependencies = [
        ("gestor", "0020_seed_santos_public_catalog"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(refresh_powerbi_reader, migrations.RunPython.noop),
    ]
