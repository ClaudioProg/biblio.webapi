# 📁 src/gestor/presentation/views.py
from django.db.models import Q
from django.core.cache import cache
from django.conf import settings
from rest_framework import viewsets, filters, permissions
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from django.db import connection

from gestor.domain.entities.livro import Livro
from gestor.domain.entities.unidade import Unidade
from gestor.domain.entities.livro_unidade import LivroUnidade
from gestor.domain.entities.genero import Genero
from gestor.domain.entities.tipo_obra import TipoObra
from gestor.domain.entities.usuario import Usuario
from gestor.presentation.serializers import (
    LivroSerializer,
    UnidadeSerializer,
    LivroUnidadeSerializer,
    UsuarioSerializer,
)
from gestor.infrastructure.external_book_services import (
    OpenLibraryLookupService,
    ExternalServiceError,
    InvalidIsbnError,
    IsbnNotFoundError,
)
from gestor.infrastructure.translation_service import TranslationService

# =========================================================
# ViewSets sem paginação (array puro) e com acesso liberado
# =========================================================

class UnidadeViewSet(viewsets.ModelViewSet):
    queryset = Unidade.objects.all().order_by("id")
    serializer_class = UnidadeSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nome", "endereco", "telefone", "email", "site"]
    ordering_fields = ["id", "nome"]
    ordering = ["id"]

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        s = self.get_serializer(qs, many=True)
        return Response(s.data)


class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all().order_by("id")
    serializer_class = UsuarioSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nome", "email", "telefone", "documento", "observacoes"]
    ordering_fields = ["id", "nome", "email", "ativo"]
    ordering = ["id"]

    def get_queryset(self):
        qs = super().get_queryset()
        ativo = self.request.query_params.get("ativo")
        if ativo is not None:
            ativo_bool = ativo.lower() in ["true", "1", "yes"]
            qs = qs.filter(ativo=ativo_bool)
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        s = self.get_serializer(qs, many=True)
        return Response(s.data)


class LivroUnidadeViewSet(viewsets.ModelViewSet):
    queryset = (
        LivroUnidade.objects.all()
        .select_related("livro", "unidade")
        .order_by("id")
    )
    serializer_class = LivroUnidadeSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["id"]
    ordering = ["id"]

    # ✅ Permite buscar por livro ou unidade via query params
    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params

        livro_id = p.get("livro")
        if livro_id:
            qs = qs.filter(livro_id=livro_id)

        unidade_id = p.get("unidade")
        if unidade_id:
            qs = qs.filter(unidade_id=unidade_id)

        return qs

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        s = self.get_serializer(qs, many=True)
        return Response(s.data)


class LivroViewSet(viewsets.ModelViewSet):
    """
    GET /gestor/livros/?titulo=...&autor=...&tipo_obra=ID&editora=...&isbn=...&unidades=1,2
    Suporta também ?unidades=NOME_DA_UNIDADE (exato ou parcial).
    """
    serializer_class = LivroSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["titulo", "autor", "editora", "isbn"]
    ordering_fields = ["id", "titulo"]
    ordering = ["id"]

    def get_queryset(self):
        qs = (
            Livro.objects.all()
            .select_related("tipo_obra")
            .order_by("id")
        )

        p = self.request.query_params

        titulo = p.get("titulo")
        if titulo:
            qs = qs.filter(titulo__icontains=titulo)

        autor = p.get("autor")
        if autor:
            qs = qs.filter(autor__icontains=autor)

        tipo_obra = p.get("tipo_obra")
        if tipo_obra:
            qs = qs.filter(tipo_obra_id=tipo_obra)

        editora = p.get("editora")
        if editora:
            qs = qs.filter(editora__icontains=editora)

        isbn = p.get("isbn")
        if isbn:
            qs = qs.filter(isbn__icontains=isbn)

        unidades = p.get("unidades")
        if unidades:
            raw = [u.strip() for u in unidades.split(",") if u.strip()]
            ids = [int(u) for u in raw if u.isdigit()]
            nomes = [u for u in raw if not u.isdigit()]
            livro_ids_q = Q()

            if ids:
                livro_ids_q |= Q(
                    id__in=LivroUnidade.objects.filter(
                        unidade_id__in=ids
                    ).values_list("livro_id", flat=True)
                )

            if nomes:
                nome_busca = " ".join(nomes)
                unidade_ids = Unidade.objects.filter(
                    nome__icontains=nome_busca
                ).values_list("id", flat=True)

                if unidade_ids:
                    livro_ids_q |= Q(
                        id__in=LivroUnidade.objects.filter(
                            unidade_id__in=list(unidade_ids)
                        ).values_list("livro_id", flat=True)
                    )

            if livro_ids_q:
                qs = qs.filter(livro_ids_q).distinct()

        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("titulo", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Busca parcial por título"),
            OpenApiParameter("autor", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Busca parcial por autor"),
            OpenApiParameter("tipo_obra", OpenApiTypes.INT, OpenApiParameter.QUERY, description="ID exato do tipo de obra"),
            OpenApiParameter("editora", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Busca parcial por editora"),
            OpenApiParameter("isbn", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Busca parcial por ISBN"),
            OpenApiParameter(
                "unidades",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description="IDs separados por vírgula (ex.: 1,2) ou nome da unidade (ex.: Central). Aceita múltiplos."
            ),
            OpenApiParameter("search", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Busca livre (DRF SearchFilter)"),
            OpenApiParameter("ordering", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Ordenação (ex.: titulo ou -titulo)"),
        ]
    )
    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        s = self.get_serializer(qs, many=True)
        return Response(s.data)


# ---------- Endpoint utilitário ----------
@api_view(["GET"])
def dados_iniciais(_request):
    generos = Genero.objects.all().values("id", "nome")
    unidades = Unidade.objects.all().values("id", "nome", "endereco", "telefone", "email", "site")
    tipos = TipoObra.objects.all().values("id", "nome")
    return Response({
        "generos": list(generos),
        "unidades": list(unidades),
        "tipo_obras": list(tipos),
    })


# --- DEBUG: Info do banco em uso ---
@api_view(["GET"])
def db_info(_request):
    cfg = connection.settings_dict
    return Response({
        "vendor": connection.vendor,
        "name": cfg.get("NAME"),
        "user": cfg.get("USER"),
        "host": cfg.get("HOST"),
    })


@extend_schema(
    parameters=[
        OpenApiParameter(
            "isbn",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=True,
            description="ISBN-10 ou ISBN-13",
        ),
    ],
    responses={
        200: OpenApiTypes.OBJECT,
        400: OpenApiTypes.OBJECT,
        404: OpenApiTypes.OBJECT,
        503: OpenApiTypes.OBJECT,
    },
)
@api_view(["GET"])
def isbn_lookup(request):
    raw_isbn = (request.query_params.get("isbn") or "").strip()
    if not raw_isbn:
        return Response({"detail": "Parâmetro isbn é obrigatório."}, status=400)

    cache_key = f"isbn_lookup:{raw_isbn}"
    cached = cache.get(cache_key)
    if cached:
        cached["meta"]["cache_hit"] = True
        return Response(cached)

    lookup_service = OpenLibraryLookupService()
    translation_service = TranslationService()

    try:
        base_payload = lookup_service.lookup(raw_isbn)
    except InvalidIsbnError as exc:
        return Response({"detail": str(exc)}, status=400)
    except IsbnNotFoundError as exc:
        return Response({"detail": str(exc)}, status=404)
    except ExternalServiceError as exc:
        return Response({"detail": str(exc)}, status=503)

    translated_payload, translation_meta = translation_service.translate_book_payload(base_payload)

    response_payload = {
        "data": translated_payload,
        "meta": {
            "source": "openlibrary",
            "translation_provider": translation_meta.get("provider", "none"),
            "translated_fields": translation_meta.get("translated_fields", []),
            "warnings": translation_meta.get("warnings", []),
            "cache_hit": False,
        },
    }

    cache.set(cache_key, response_payload, timeout=settings.ISBN_LOOKUP_CACHE_TTL_SECONDS)
    return Response(response_payload)
