from django.db import migrations

def backfill(apps, schema_editor):
    Subscription = apps.get_model("memberships", "Subscription")
    for s in Subscription.objects.all().iterator():
        if s.season_id is None:
            s.season_id = s.product.season_id
            s.save(update_fields=["season"])

class Migration(migrations.Migration):

    dependencies = [
        ("memberships", "0003_alter_subscription_unique_together_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
