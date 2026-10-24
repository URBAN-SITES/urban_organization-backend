from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.user_settings.serializers.user_settings import UserSettingsSerializer
from core.modules.user_settings.services.user_settings import UserSettingsService


@extend_schema(tags=["Perfil"])
class UserSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get my preferences", responses=UserSettingsSerializer)
    def get(self, request):
        instance = UserSettingsService.get(request.user)
        return Response(UserSettingsSerializer(instance).data)

    @extend_schema(
        summary="Update my preferences",
        request=UserSettingsSerializer,
        responses=UserSettingsSerializer,
    )
    def patch(self, request):
        serializer = UserSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance = UserSettingsService.update(request.user, serializer.validated_data)
        return Response(UserSettingsSerializer(instance).data)
