import os

from django.contrib.auth.hashers import make_password
from django.db import migrations


def ensure_claudio_admin(apps, schema_editor):
    User = apps.get_model("auth", "User")

    username = os.getenv("BIBLIO_CLAUDIO_USERNAME", "").strip()
    password = os.getenv("BIBLIO_CLAUDIO_PASSWORD", "")
    email = os.getenv("BIBLIO_CLAUDIO_EMAIL", "").strip()

    if not username or not password:
        return

    user = User.objects.filter(username__iexact=username).first()
    if user is None:
        user = User(username=username)

    user.username = username
    user.email = email or user.email
    user.is_active = True
    user.is_staff = True
    user.is_superuser = True
    user.password = make_password(password)
    user.save()


class Migration(migrations.Migration):

    dependencies = [
        ("gestor", "0018_powerbi_reader_group"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(ensure_claudio_admin, migrations.RunPython.noop),
    ]
