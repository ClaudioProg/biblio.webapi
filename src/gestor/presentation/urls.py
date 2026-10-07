# 📁 src/gestor/presentation/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from gestor.presentation.views import (
    LivroViewSet,
    UnidadeViewSet,
    LivroUnidadeViewSet,
    UsuarioViewSet,
    EmprestimoViewSet,
    auth_login,
    auth_logout,
    auth_me,
    auth_change_password,
    analytics_resumo,
    analytics_territorio,
    dados_iniciais,
    isbn_lookup,
)

# ---------- Roteador padrão DRF ----------
router = DefaultRouter()
router.register(r"livros", LivroViewSet, basename="livro")
router.register(r"unidades", UnidadeViewSet, basename="unidade")
router.register(r"livro-unidades", LivroUnidadeViewSet, basename="livro-unidade")
router.register(r"usuarios", UsuarioViewSet, basename="usuario")
router.register(r"emprestimos", EmprestimoViewSet, basename="emprestimo")

# ---------- URLs principais ----------
urlpatterns = [
    path("auth/login/", auth_login, name="auth-login"),
    path("auth/logout/", auth_logout, name="auth-logout"),
    path("auth/me/", auth_me, name="auth-me"),
    path("auth/change-password/", auth_change_password, name="auth-change-password"),
    path("analytics/resumo/", analytics_resumo, name="analytics-resumo"),
    path("analytics/territorio/", analytics_territorio, name="analytics-territorio"),
    path("dados-iniciais/", dados_iniciais, name="dados-iniciais"),
    path("livros/isbn-lookup/", isbn_lookup, name="isbn-lookup"),
    path("", include(router.urls)),
]
