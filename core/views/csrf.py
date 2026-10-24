from django.middleware import csrf
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


@extend_schema(tags=["Conta e Sessões"])
class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Issue the CSRF cookie",
        description="The front end calls this before login so the `csrftoken` cookie exists for the writes that follow.",
        responses={204: None},
    )
    def get(self, request):
        csrf.get_token(request)  # the middleware sets the cookie on the response
        return Response(status=status.HTTP_204_NO_CONTENT)
