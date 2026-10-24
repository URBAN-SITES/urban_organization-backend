from core.modules.user_settings.models.user_settings import UserSettings


class UserSettingsService:
    @staticmethod
    def get(user):
        settings, _ = UserSettings.objects.get_or_create(user=user)
        return settings

    @staticmethod
    def update(user, values):
        settings = UserSettingsService.get(user)
        for field, value in values.items():
            setattr(settings, field, value)
        if values:
            settings.save(update_fields=list(values))
        return settings
