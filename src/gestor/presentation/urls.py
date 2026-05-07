# 📁 src/gestor/presentation/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from gestor.presentation.views import (
    LivroViewSet,
    UnidadeViewSet,
    LivroUnidadeViewSet,
    UsuarioViewSet,
    dados_iniciais,
    isbn_lookup,
    db_info,  # 👈 adiciona aqui
)

# ---------- Roteador padrão DRF ----------
router = DefaultRouter()
router.register(r"livros", LivroViewSet, basename="livro")
router.register(r"unidades", UnidadeViewSet, basename="unidade")
router.register(r"livro-unidades", LivroUnidadeViewSet, basename="livro-unidade")
router.register(r"usuarios", UsuarioViewSet, basename="usuario")

# ---------- URLs principais ----------
urlpatterns = [
    path("dados-iniciais/", dados_iniciais, name="dados-iniciais"),
    path("livros/isbn-lookup/", isbn_lookup, name="isbn-lookup"),
    path("debug/db-info/", db_info, name="db-info"),  # 👈 nova rota
    path("", include(router.urls)),
]
