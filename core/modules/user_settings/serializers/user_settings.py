from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from core.modules.user_settings.models.user_settings import UserSettings
from core.modules.user_settings.response_messages import MSG_INVALID_TIMEZONE


class UserSettingsSerializer(serializers.ModelSerializer):
    locale = serializers.RegexField(
        r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$", max_length=10
    )

    class Meta:
        model = UserSettings
        fields = (
            "theme",
            "locale",
            "timezone",
            "push_enabled",
            "email_product",
            "email_weekly_digest",
            "email_security",
            "email_assigned",
            "email_mentions",
            "email_deadlines",
            "app_comments",
            "app_status",
            "app_ai",
            "date_format",
            "week_start",
            "compact_cards",
            "show_completed",
        )

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError, ValueError:
            raise serializers.ValidationError(MSG_INVALID_TIMEZONE) from None
        return value
