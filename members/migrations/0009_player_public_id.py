from django.db import migrations, models
import uuid


def populate_public_ids(apps, schema_editor):
    Player = apps.get_model("members", "Player")
    # If your table is big, consider iterating in chunks
    for p in Player.objects.filter(public_id__isnull=True):
        p.public_id = uuid.uuid4()
        p.save(update_fields=["public_id"])


def noop(apps, schema_editor):
    # We don't attempt to null-out public_id on reverse;
    # the following AlterField reverse will allow nulls again.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0008_notice_dynamicquestion_description_directmessage"),
    ]

    operations = [
        # 1) Add field, allow NULL and no unique yet
        migrations.AddField(
            model_name="player",
            name="public_id",
            field=models.UUIDField(null=True, editable=False),
        ),

        # 2) Populate existing rows
        migrations.RunPython(populate_public_ids, reverse_code=noop),

        # 3) Enforce NOT NULL + UNIQUE (and keep default for future rows)
        migrations.AlterField(
            model_name="player",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
        ),
        # NOTE: AlterField will implicitly set null=False because UUIDField defaults to null=False
        # If your linter wants it explicit, use: models.UUIDField(default=uuid.uuid4, unique=True, editable=False, null=False)
    ]
