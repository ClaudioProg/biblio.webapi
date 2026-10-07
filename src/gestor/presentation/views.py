# 📁 src/gestor/presentation/views.py
from django.db.models import Count, Q, Sum
from django.db.models.deletion import ProtectedError
from django.core.cache import cache
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets, filters, permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.authentication import BasicAuthentication, TokenAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from gestor.domain.entities.livro import Livro
from gestor.domain.entities.unidade import Unidade
from gestor.domain.entities.livro_unidade import LivroUnidade
from gestor.domain.entities.genero import Genero
from gestor.domain.entities.tipo_obra import TipoObra
from gestor.domain.entities.usuario import Usuario
from gestor.domain.entities.emprestimo import Emprestimo
from gestor.presentation.serializers import (
    LivroSerializer,
    UnidadeSerializer,
    LivroUnidadeSerializer,
    UsuarioSerializer,
    EmprestimoSerializer,
)
from gestor.infrastructure.external_book_services import (
    OpenLibraryLookupService,
    ExternalServiceError,
    InvalidIsbnError,
    IsbnNotFoundError,
)
from gestor.infrastructure.translation_service import TranslationService
from gestor.infrastructure.territory_service import (
    neighborhood_name_by_code,
    territory_payload,
)
from gestor.infrastructure.powerbi_service import build_powerbi_dataset

# =========================================================
# Autenticação da equipe gestora
# =========================================================

POWERBI_READER_GROUP = "powerbi_reader"


class PowerBIAnalyticsPermission(permissions.BasePermission):
    message = "Conta sem permissão para acessar o dataset analítico do Power BI."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or not user.is_active:
            return False

        return bool(
            user.is_staff
            or user.is_superuser
            or user.groups.filter(name=POWERBI_READER_GROUP).exists()
        )


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def auth_login(request):
    username = str(request.data.get("username") or "").strip()
    password = str(request.data.get("password") or "")

    if not username or not password:
        return Response(
            {"detail": "Informe usuário e senha."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(request=request, username=username, password=password)
    if user is None or not user.is_active:
        return Response(
            {"detail": "Credenciais inválidas."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not (user.is_staff or user.is_superuser):
        return Response(
            {"detail": "Conta sem permissão para acessar a gestão da plataforma."},
            status=status.HTTP_403_FORBIDDEN,
        )

    token, _ = Token.objects.get_or_create(user=user)
    role = "admin" if user.is_superuser else ("staff" if user.is_staff else "usuario")

    return Response({
        "token": token.key,
        "user": {
            "username": user.get_username(),
            "name": user.get_full_name() or user.get_username(),
            "role": role,
        },
    })


@api_view(["POST"])
def auth_logout(request):
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
def auth_me(request):
    user = request.user
    role = "admin" if user.is_superuser else ("staff" if user.is_staff else "usuario")
    return Response({
        "username": user.get_username(),
        "name": user.get_full_name() or user.get_username(),
        "role": role,
    })


@api_view(["POST"])
def auth_change_password(request):
    user = request.user
    current_password = str(request.data.get("current_password") or "")
    new_password = str(request.data.get("new_password") or "")

    if not user.check_password(current_password):
        return Response(
            {"current_password": "Senha atual incorreta."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        validate_password(new_password, user=user)
    except DjangoValidationError as exc:
        return Response(
            {"new_password": list(exc.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.set_password(new_password)
    user.save(update_fields=["password"])

    Token.objects.filter(user=user).delete()
    token = Token.objects.create(user=user)

    return Response({
        "detail": "Senha alterada com sucesso.",
        "token": token.key,
    })


# =========================================================
# ViewSets sem paginação (array puro) e autenticados
# =========================================================

class ProtectLoanHistoryMixin:
    protected_error_message = (
        "Este registro não pode ser excluído porque possui histórico de empréstimos. "
        "Preserve o histórico e, quando aplicável, inative ou corrija o cadastro."
    )

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": self.protected_error_message},
                status=status.HTTP_409_CONFLICT,
            )


class UnidadeViewSet(ProtectLoanHistoryMixin, viewsets.ModelViewSet):
    queryset = Unidade.objects.all().order_by("id")
    serializer_class = UnidadeSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "nome",
        "endereco",
        "telefone",
        "email",
        "site",
        "ibge_bairro_codigo",
    ]
    ordering_fields = ["id", "nome"]
    ordering = ["id"]

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        s = self.get_serializer(qs, many=True)
        return Response(s.data)


class UsuarioViewSet(ProtectLoanHistoryMixin, viewsets.ModelViewSet):
    queryset = Usuario.objects.all().order_by("id")
    serializer_class = UsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]
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


class EmprestimoViewSet(viewsets.ModelViewSet):
    queryset = (
        Emprestimo.objects.all()
        .select_related("livro", "usuario", "unidade")
        .order_by("-data_emprestimo", "-id")
    )
    serializer_class = EmprestimoSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["livro__titulo", "usuario__nome", "unidade__nome", "status", "observacoes"]
    ordering_fields = ["id", "data_emprestimo", "data_prevista_devolucao", "status"]
    ordering = ["-data_emprestimo", "-id"]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params

        livro_id = p.get("livro")
        if livro_id:
            qs = qs.filter(livro_id=livro_id)

        usuario_id = p.get("usuario")
        if usuario_id:
            qs = qs.filter(usuario_id=usuario_id)

        unidade_id = p.get("unidade")
        if unidade_id:
            qs = qs.filter(unidade_id=unidade_id)

        status = p.get("status")
        if status:
            qs = qs.filter(status=status)

        return qs

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        s = self.get_serializer(qs, many=True)
        return Response(s.data)

    def destroy(self, request, *args, **kwargs):
        return Response(
            {
                "detail": (
                    "Empréstimos fazem parte do histórico de circulação e não podem "
                    "ser excluídos. Corrija o registro ou finalize a devolução."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class LivroUnidadeViewSet(viewsets.ModelViewSet):
    queryset = (
        LivroUnidade.objects.all()
        .select_related("livro", "unidade")
        .order_by("id")
    )
    serializer_class = LivroUnidadeSerializer
    permission_classes = [permissions.IsAuthenticated]
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

    def destroy(self, request, *args, **kwargs):
        relation = self.get_object()
        has_open_loans = Emprestimo.objects.filter(
            livro=relation.livro,
            unidade=relation.unidade,
            status=Emprestimo.STATUS_ABERTO,
        ).exists()

        if has_open_loans:
            return Response(
                {
                    "detail": (
                        "O vínculo livro/unidade não pode ser removido enquanto "
                        "houver empréstimos abertos nessa unidade."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        return super().destroy(request, *args, **kwargs)


class LivroViewSet(ProtectLoanHistoryMixin, viewsets.ModelViewSet):
    """
    GET /gestor/livros/?titulo=...&autor=...&tipo_obra=ID&editora=...&isbn=...&unidades=1,2
    Suporta também ?unidades=NOME_DA_UNIDADE (exato ou parcial).
    """
    serializer_class = LivroSerializer
    permission_classes = [permissions.IsAuthenticated]
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


# ---------- Analytics agregados (base para dashboard / Power BI) ----------
@api_view(["GET"])
def analytics_resumo(_request):
    total_exemplares = (
        LivroUnidade.objects.aggregate(total=Sum("exemplares")).get("total") or 0
    )

    emprestimos_por_status = {
        row["status"]: row["total"]
        for row in Emprestimo.objects.values("status").annotate(total=Count("id"))
    }

    por_genero = list(
        LivroUnidade.objects.values("livro__genero__nome")
        .annotate(
            titulos=Count("livro_id", distinct=True),
            exemplares=Sum("exemplares"),
        )
        .order_by("-exemplares", "livro__genero__nome")
    )

    por_tipo = list(
        LivroUnidade.objects.values("livro__tipo_obra__nome")
        .annotate(
            titulos=Count("livro_id", distinct=True),
            exemplares=Sum("exemplares"),
        )
        .order_by("-exemplares", "livro__tipo_obra__nome")
    )

    emprestimos_unidade = {
        row["unidade_id"]: {
            "emprestimos_total": row["total"],
            "emprestimos_abertos": row["abertos"],
            "emprestimos_devolvidos": row["devolvidos"],
        }
        for row in Emprestimo.objects.exclude(unidade_id=None)
        .values("unidade_id")
        .annotate(
            total=Count("id"),
            abertos=Count("id", filter=Q(status=Emprestimo.STATUS_ABERTO)),
            devolvidos=Count("id", filter=Q(status=Emprestimo.STATUS_DEVOLVIDO)),
        )
    }

    por_unidade = []
    for row in (
        LivroUnidade.objects.values(
            "unidade_id",
            "unidade__nome",
            "unidade__ibge_bairro_codigo",
            "unidade__latitude",
            "unidade__longitude",
        )
        .annotate(
            titulos=Count("livro_id", distinct=True),
            exemplares=Sum("exemplares"),
        )
        .order_by("unidade__nome")
    ):
        movimento = emprestimos_unidade.get(
            row["unidade_id"],
            {
                "emprestimos_total": 0,
                "emprestimos_abertos": 0,
                "emprestimos_devolvidos": 0,
            },
        )
        bairro_codigo = row.get("unidade__ibge_bairro_codigo")
        por_unidade.append({
            **row,
            **movimento,
            "ibge_bairro_codigo": bairro_codigo,
            "ibge_bairro_nome": neighborhood_name_by_code(bairro_codigo),
            "latitude": row.get("unidade__latitude"),
            "longitude": row.get("unidade__longitude"),
        })

    return Response({
        "meta": {
            "escopo": "dados agregados da plataforma Bibliotecas Conectadas",
            "contém_dados_pessoais": False,
            "observacao": (
                "Estes indicadores descrevem o acervo e a circulação registrada na "
                "plataforma. Não representam, por si só, a demanda sociodemográfica."
            ),
        },
        "resumo": {
            "titulos": Livro.objects.count(),
            "exemplares": total_exemplares,
            "unidades": Unidade.objects.count(),
            "usuarios_ativos": Usuario.objects.filter(ativo=True).count(),
            "emprestimos_total": Emprestimo.objects.count(),
            "emprestimos_abertos": emprestimos_por_status.get(
                Emprestimo.STATUS_ABERTO, 0
            ),
            "emprestimos_devolvidos": emprestimos_por_status.get(
                Emprestimo.STATUS_DEVOLVIDO, 0
            ),
        },
        "acervo_por_genero": [
            {
                "genero": row["livro__genero__nome"] or "Não informado",
                "titulos": row["titulos"],
                "exemplares": row["exemplares"] or 0,
            }
            for row in por_genero
        ],
        "acervo_por_tipo": [
            {
                "tipo_obra": row["livro__tipo_obra__nome"] or "Não informado",
                "titulos": row["titulos"],
                "exemplares": row["exemplares"] or 0,
            }
            for row in por_tipo
        ],
        "por_unidade": [
            {
                "unidade_id": row["unidade_id"],
                "unidade": row["unidade__nome"],
                "ibge_bairro_codigo": row.get("ibge_bairro_codigo"),
                "ibge_bairro_nome": row.get("ibge_bairro_nome"),
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "titulos": row["titulos"],
                "exemplares": row["exemplares"] or 0,
                "emprestimos_total": row["emprestimos_total"],
                "emprestimos_abertos": row["emprestimos_abertos"],
                "emprestimos_devolvidos": row["emprestimos_devolvidos"],
            }
            for row in por_unidade
        ],
    })


@extend_schema(
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
@authentication_classes([BasicAuthentication, TokenAuthentication])
@permission_classes([PowerBIAnalyticsPermission])
def analytics_powerbi(_request):
    return Response(build_powerbi_dataset())


@extend_schema(
    parameters=[
        OpenApiParameter(
            "codigo",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            description="Código IBGE exato do bairro.",
        ),
        OpenApiParameter(
            "bairro",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            description="Busca parcial pelo nome do bairro.",
        ),
    ],
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
def analytics_territorio(request):
    payload = territory_payload(
        neighborhood_code=(request.query_params.get("codigo") or "").strip(),
        neighborhood_name=(request.query_params.get("bairro") or "").strip(),
    )
    return Response(payload)


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
