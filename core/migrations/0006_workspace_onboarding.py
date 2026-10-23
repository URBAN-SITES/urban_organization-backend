from django.db import migrations, models
import django.core.validators
import core.modules.organizations.models.organization


def populate_workspace_slugs(apps, schema_editor):
    Organization = apps.get_model("core", "Organization")
    for organization in (
        Organization.objects.using(schema_editor.connection.alias)
        .filter(slug__isnull=True)
        .iterator()
    ):
        organization.slug = f"workspace-{organization.pk.hex}"
        organization.save(using=schema_editor.connection.alias, update_fields=["slug"])


class Migration(migrations.Migration):
    dependencies = [("core", "0005_chat_sector_mentions_tasks")]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="slug",
            field=models.SlugField(max_length=63, null=True, unique=True),
        ),
        migrations.RunPython(populate_workspace_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="organization",
            name="slug",
            field=models.SlugField(
                default=core.modules.organizations.models.organization.default_organization_slug,
                max_length=63,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
                        "Use lowercase letters, numbers and single hyphens.",
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="team_size",
            field=models.CharField(
                blank=True,
                choices=[
                    ("1", "Just me"),
                    ("2-10", "2 to 10 people"),
                    ("11-50", "11 to 50 people"),
                    ("51-200", "51 to 200 people"),
                    ("201+", "More than 200 people"),
                ],
                default="",
                max_length=10,
                verbose_name="team size",
            ),
        ),
        migrations.AddField(
            model_name="organizationinvite",
            name="sectors",
            field=models.ManyToManyField(
                blank=True, related_name="organization_invites", to="core.sector"
            ),
        ),
    ]
