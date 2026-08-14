# Generated manually — grupo kb_supereditor

from django.conf import settings
from django.db import migrations


def ensure_supereditor_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    name = getattr(settings, "KB_SUPEREDITOR_GROUP", "kb_supereditor")
    Group.objects.get_or_create(name=name)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("kb", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(ensure_supereditor_group, noop_reverse),
    ]
