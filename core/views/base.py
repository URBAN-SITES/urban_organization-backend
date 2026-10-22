from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet


class OwnedModelViewSet(ModelViewSet):
    """
    Full CRUD scoped to the logged user, for models inheriting BaseModel.
    DELETE is a soft delete.

        class ProductViewSet(OwnedModelViewSet):
            queryset = Product.objects.all()
            serializer_class = ProductSerializer

        # urls.py
        router = DefaultRouter()
        router.register("products", ProductViewSet)
        urlpatterns += router.urls
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user, is_active=True)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete()
