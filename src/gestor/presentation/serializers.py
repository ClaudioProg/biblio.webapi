# 📄 src/gestor/presentation/serializers.py
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from gestor.domain.entities.livro import Livro
from gestor.domain.entities.unidade import Unidade
from gestor.domain.entities.livro_unidade import LivroUnidade
from gestor.domain.entities.tipo_obra import TipoObra
from gestor.domain.entities.genero import Genero  # necessário porque o Livro usa "genero" (FK)
from gestor.domain.entities.usuario import Usuario
from gestor.domain.entities.emprestimo import Emprestimo
from gestor.infrastructure.territory_service import (
    is_valid_neighborhood_code,
    neighborhood_name_by_code,
)


# ============== Acessos à plataforma ==============
class AccessAccountSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(max_length=150)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=["admin", "staff"])
    active = serializers.BooleanField(default=True)
    password = serializers.CharField(
        write_only=True,
        required=False,
        trim_whitespace=False,
    )
    last_login = serializers.DateTimeField(read_only=True, allow_null=True)

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "username": instance.username,
            "first_name": instance.first_name,
            "last_name": instance.last_name,
            "email": instance.email,
            "role": "admin" if instance.is_superuser else "staff",
            "active": instance.is_active,
            "last_login": instance.last_login,
        }

    def validate_username(self, value):
        username = str(value or "").strip()
        if not username:
            raise serializers.ValidationError("Informe o nome de usuário.")

        User = get_user_model()
        qs = User.objects.filter(username__iexact=username)
        instance = getattr(self, "instance", None)
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Já existe uma conta com este nome de usuário."
            )
        return username

    def validate(self, attrs):
        password = attrs.get("password")
        if self.instance is None and not password:
            raise serializers.ValidationError({
                "password": "Informe uma senha temporária para a nova conta."
            })

        if password:
            candidate = self.instance or get_user_model()(username=attrs.get("username", ""))
            validate_password(password, user=candidate)

        return attrs

    def create(self, validated_data):
        User = get_user_model()
        password = validated_data.pop("password")
        role = validated_data.pop("role")
        active = validated_data.pop("active", True)

        user = User(
            **validated_data,
            is_active=active,
            is_staff=True,
            is_superuser=(role == "admin"),
        )
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        validated_data.pop("password", None)
        role = validated_data.pop(
            "role",
            "admin" if instance.is_superuser else "staff",
        )
        active = validated_data.pop("active", instance.is_active)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.is_active = active
        instance.is_staff = True
        instance.is_superuser = role == "admin"
        instance.save()
        return instance


class AccessPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )

    def validate_password(self, value):
        validate_password(value, user=self.context.get("user"))
        return value


# ============== Unidades ==============
class UnidadeSerializer(serializers.ModelSerializer):
    ibge_bairro_nome = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Unidade
        fields = [
            "id",
            "nome",
            "endereco",
            "telefone",
            "email",
            "site",
            "ibge_bairro_codigo",
            "ibge_bairro_nome",
            "latitude",
            "longitude",
        ]

    def get_ibge_bairro_nome(self, obj):
        return neighborhood_name_by_code(obj.ibge_bairro_codigo)

    def validate_ibge_bairro_codigo(self, value):
        code = str(value or "").strip()
        if not code:
            return None
        if not is_valid_neighborhood_code(code):
            raise serializers.ValidationError(
                "Código de bairro inválido para o recorte oficial de Santos/IBGE."
            )
        return code

    def validate_latitude(self, value):
        if value is not None and not (-90 <= value <= 90):
            raise serializers.ValidationError("Latitude inválida.")
        return value

    def validate_longitude(self, value):
        if value is not None and not (-180 <= value <= 180):
            raise serializers.ValidationError("Longitude inválida.")
        return value


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ["id", "nome", "email", "telefone", "documento", "ativo", "observacoes"]


class EmprestimoSerializer(serializers.ModelSerializer):
    livro = serializers.PrimaryKeyRelatedField(queryset=Livro.objects.all())
    unidade = serializers.PrimaryKeyRelatedField(queryset=Unidade.objects.all(), required=True)
    usuario = serializers.PrimaryKeyRelatedField(queryset=Usuario.objects.all())
    livro_titulo = serializers.CharField(source="livro.titulo", read_only=True)
    unidade_nome = serializers.CharField(source="unidade.nome", read_only=True)
    usuario_nome = serializers.CharField(source="usuario.nome", read_only=True)
    data_prevista_devolucao = serializers.DateField(required=False, allow_null=True)
    data_devolucao = serializers.DateField(required=False, allow_null=True)

    class Meta:
        model = Emprestimo
        fields = [
            "id",
            "livro",
            "unidade",
            "usuario",
            "livro_titulo",
            "unidade_nome",
            "usuario_nome",
            "data_emprestimo",
            "data_prevista_devolucao",
            "data_devolucao",
            "status",
            "observacoes",
        ]

    def _lock_and_check_capacity(self, livro, unidade, status, exclude_pk=None):
        """
        Serializa alterações que consomem disponibilidade do mesmo livro/unidade.

        O select_for_update precisa ocorrer dentro de transaction.atomic. Assim,
        dois empréstimos simultâneos do último exemplar não podem ambos passar
        pela contagem antes da gravação do primeiro.
        """
        if status != Emprestimo.STATUS_ABERTO:
            return

        livro_unidade = (
            LivroUnidade.objects.select_for_update()
            .filter(livro=livro, unidade=unidade)
            .first()
        )
        if not livro_unidade or livro_unidade.exemplares <= 0:
            raise serializers.ValidationError({
                "unidade": (
                    "Este livro não possui exemplares disponíveis na unidade selecionada."
                )
            })

        emprestimos_abertos = Emprestimo.objects.filter(
            livro=livro,
            unidade=unidade,
            status=Emprestimo.STATUS_ABERTO,
        )
        if exclude_pk:
            emprestimos_abertos = emprestimos_abertos.exclude(pk=exclude_pk)

        if emprestimos_abertos.count() >= livro_unidade.exemplares:
            raise serializers.ValidationError({
                "livro": (
                    "Sem disponibilidade deste livro na unidade selecionada "
                    "para novo empréstimo."
                )
            })

    def validate_data_emprestimo(self, value):
        """Validar que data de empréstimo não é futura."""
        if value and value > timezone.localdate():
            raise serializers.ValidationError("Data de empréstimo não pode estar no futuro.")
        return value

    def validate_observacoes(self, value):
        """Sanitizar observações: trim e limite de caracteres."""
        if value:
            value = str(value).strip()
            if len(value) > 1000:
                raise serializers.ValidationError("Observações não devem exceder 1000 caracteres.")
        return value or None

    def validate(self, attrs):
        # Limpar strings vazias em campos de data opcionais
        if attrs.get("data_prevista_devolucao") == "":
            attrs["data_prevista_devolucao"] = None
        if attrs.get("data_devolucao") == "":
            attrs["data_devolucao"] = None

        livro = attrs.get("livro", getattr(self.instance, "livro", None))
        unidade = attrs.get("unidade", getattr(self.instance, "unidade", None))
        data_emprestimo = attrs.get("data_emprestimo", getattr(self.instance, "data_emprestimo", None))
        data_prevista = attrs.get(
            "data_prevista_devolucao",
            getattr(self.instance, "data_prevista_devolucao", None),
        )
        data_devolucao = attrs.get("data_devolucao", getattr(self.instance, "data_devolucao", None))
        status = attrs.get("status", getattr(self.instance, "status", Emprestimo.STATUS_ABERTO))

        if not unidade:
            raise serializers.ValidationError({"unidade": "Unidade é obrigatória no empréstimo."})

        if not livro:
            raise serializers.ValidationError({"livro": "Livro é obrigatório no empréstimo."})

        usuario = attrs.get("usuario", getattr(self.instance, "usuario", None))
        if status == Emprestimo.STATUS_ABERTO and usuario and not usuario.ativo:
            raise serializers.ValidationError({
                "usuario": "Usuário inativo não pode manter ou receber empréstimo aberto."
            })

        livro_unidade = LivroUnidade.objects.filter(livro=livro, unidade=unidade).first()
        if not livro_unidade or livro_unidade.exemplares <= 0:
            raise serializers.ValidationError(
                {"unidade": "Este livro não possui exemplares disponíveis na unidade selecionada."}
            )

        if status == Emprestimo.STATUS_ABERTO:
            emprestimos_abertos = Emprestimo.objects.filter(
                livro=livro,
                unidade=unidade,
                status=Emprestimo.STATUS_ABERTO,
            )
            if self.instance and self.instance.pk:
                emprestimos_abertos = emprestimos_abertos.exclude(pk=self.instance.pk)

            if emprestimos_abertos.count() >= livro_unidade.exemplares:
                raise serializers.ValidationError(
                    {"livro": "Sem disponibilidade deste livro na unidade selecionada para novo empréstimo."}
                )

        if data_prevista and data_emprestimo and data_prevista < data_emprestimo:
            raise serializers.ValidationError(
                {"data_prevista_devolucao": "Data prevista não pode ser anterior à data de empréstimo."}
            )

        if data_devolucao and data_emprestimo and data_devolucao < data_emprestimo:
            raise serializers.ValidationError(
                {"data_devolucao": "Data de devolução não pode ser anterior à data de empréstimo."}
            )

        if status == Emprestimo.STATUS_DEVOLVIDO and not data_devolucao:
            raise serializers.ValidationError(
                {"data_devolucao": "Informe a data de devolução para finalizar o empréstimo."}
            )

        if data_devolucao and status == Emprestimo.STATUS_ABERTO:
            attrs["status"] = Emprestimo.STATUS_DEVOLVIDO

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        livro = validated_data["livro"]
        unidade = validated_data["unidade"]
        status = validated_data.get("status", Emprestimo.STATUS_ABERTO)
        self._lock_and_check_capacity(livro, unidade, status)
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        livro = validated_data.get("livro", instance.livro)
        unidade = validated_data.get("unidade", instance.unidade)
        status = validated_data.get("status", instance.status)
        self._lock_and_check_capacity(
            livro,
            unidade,
            status,
            exclude_pk=instance.pk,
        )
        return super().update(instance, validated_data)


# ============== LivroUnidade (write / read) ==============
class LivroUnidadeWriteSerializer(serializers.ModelSerializer):
    # recebe ID de unidade
    unidade = serializers.PrimaryKeyRelatedField(queryset=Unidade.objects.all())

    class Meta:
        model = LivroUnidade
        fields = ["unidade", "exemplares"]


class LivroUnidadeReadSerializer(serializers.ModelSerializer):
    # devolve dados da unidade e disponibilidade atual
    unidade = UnidadeSerializer(read_only=True)
    emprestimos_abertos = serializers.SerializerMethodField()
    exemplares_disponiveis = serializers.SerializerMethodField()

    class Meta:
        model = LivroUnidade
        fields = [
            "unidade",
            "exemplares",
            "emprestimos_abertos",
            "exemplares_disponiveis",
        ]

    def get_emprestimos_abertos(self, obj):
        return Emprestimo.objects.filter(
            livro=obj.livro,
            unidade=obj.unidade,
            status=Emprestimo.STATUS_ABERTO,
        ).count()

    def get_exemplares_disponiveis(self, obj):
        return max(0, int(obj.exemplares) - self.get_emprestimos_abertos(obj))


# HÍBRIDO para manter compatibilidade com LivroUnidadeViewSet (read + write)
class LivroUnidadeSerializer(LivroUnidadeWriteSerializer):
    """
    - Na escrita (create/update), usa PrimaryKeyRelatedField (como Write).
    - Na leitura (response), serializa como Read (com Unidade detalhada).
    - Não permite reduzir o estoque abaixo dos empréstimos ainda abertos.
    """

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance
        if instance is None:
            return attrs

        unidade = attrs.get("unidade", instance.unidade)
        exemplares = attrs.get("exemplares", instance.exemplares)
        abertos = Emprestimo.objects.filter(
            livro=instance.livro,
            unidade=unidade,
            status=Emprestimo.STATUS_ABERTO,
        ).count()

        if exemplares < abertos:
            raise serializers.ValidationError({
                "exemplares": (
                    f"Não é possível reduzir para {exemplares}: existem "
                    f"{abertos} empréstimo(s) aberto(s) nesta unidade."
                )
            })

        return attrs

    def to_representation(self, instance):
        return LivroUnidadeReadSerializer(instance).data


# ============== Livro ==============
class LivroSerializer(serializers.ModelSerializer):
    # entrada (write) das unidades aninhadas
    unidades = LivroUnidadeWriteSerializer(many=True, write_only=True, required=False)

    # saída (read) detalhada
    unidades_detalhe = serializers.SerializerMethodField(read_only=True)

    # FKs como IDs (ambos opcionais do ponto de vista do serializer;
    # se o modelo exigir, validamos em runtime)
    genero = serializers.PrimaryKeyRelatedField(
        queryset=Genero.objects.all(),
        allow_null=True,
        required=False,
    )
    tipo_obra = serializers.PrimaryKeyRelatedField(
        queryset=TipoObra.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Livro
        fields = (
            "id",
            "titulo",
            "autor",
            "editora",
            "data_publicacao",
            "isbn",
            "paginas",
            "capa",
            "idioma",
            "genero",            # FK (ID)
            "tipo_obra",         # FK (ID)
            "unidades",          # write-only
            "unidades_detalhe",  # read-only
        )

    # --------- Helpers ---------
    def _clean_none(self, data: dict) -> dict:
        """Remove chaves com None para evitar tentar gravar NULL em colunas NOT NULL."""
        return {k: v for k, v in data.items() if v is not None}

    def _validate_unidades_against_open_loans(self, livro, unidades_payload):
        requested = {}
        for item in unidades_payload:
            unidade = item["unidade"]
            requested[unidade.id] = int(item.get("exemplares", 1))

        open_counts = {}
        for emprestimo in Emprestimo.objects.filter(
            livro=livro,
            status=Emprestimo.STATUS_ABERTO,
            unidade__isnull=False,
        ).values("unidade_id"):
            unidade_id = emprestimo["unidade_id"]
            open_counts[unidade_id] = open_counts.get(unidade_id, 0) + 1

        errors = []
        for unidade_id, open_count in open_counts.items():
            requested_count = requested.get(unidade_id, 0)
            if requested_count < open_count:
                unidade_nome = (
                    Unidade.objects.filter(pk=unidade_id)
                    .values_list("nome", flat=True)
                    .first()
                    or f"Unidade {unidade_id}"
                )
                errors.append(
                    f"{unidade_nome}: {open_count} empréstimo(s) aberto(s), "
                    f"mas o novo estoque informado é {requested_count}."
                )

        if errors:
            raise serializers.ValidationError({
                "unidades": [
                    "Não é possível remover uma unidade ou reduzir exemplares "
                    "abaixo da quantidade atualmente emprestada.",
                    *errors,
                ]
            })

    def _friendly_integrity_message(self, exc: IntegrityError) -> dict:
        """Mapeia mensagens comuns de integridade para respostas amigáveis."""
        raw = str(getattr(exc, "__cause__", exc))  # pega causa do DB quando existir
        low = raw.lower()

        # Duplicidade ISBN (quando unique=True)
        if "unique" in low and "isbn" in low:
            return {"isbn": "Já existe um livro com este ISBN."}

        # Chave estrangeira inválida
        if "foreign key" in low and ("genero" in low or "tipo_obra" in low):
            return {"detail": "Gênero ou tipo de obra inválido."}

        # Exemplo para unique(livro, unidade) em LivroUnidade
        if "unique" in low and ("livro" in low and "unidade" in low):
            return {"unidades": "Vínculo livro/unidade duplicado."}

        return {"detail": f"Falha de integridade: {raw}"}

    # --------- Read ---------
    def get_unidades_detalhe(self, obj):
        rows = LivroUnidade.objects.select_related("unidade").filter(livro=obj)
        return LivroUnidadeReadSerializer(rows, many=True).data

    # --------- Validate ---------
    def validate(self, attrs):
        """
        Validação defensiva:
        - remove None
        - se o modelo exigir campos NOT NULL (genero/tipo_obra), acusa antes de ir ao DB
        """
        cleaned = self._clean_none(attrs)

        # Se o modelo exigir NOT NULL, valida aqui para retornar 400 em vez de 500
        genero_field = Livro._meta.get_field("genero")
        tipo_field = Livro._meta.get_field("tipo_obra")

        if (not genero_field.null) and ("genero" not in cleaned):
            raise serializers.ValidationError({"genero": "Campo obrigatório."})

        if (not tipo_field.null) and ("tipo_obra" not in cleaned):
            raise serializers.ValidationError({"tipo_obra": "Campo obrigatório."})

        return cleaned

    # --------- Create / Update ---------
    @transaction.atomic
    def create(self, validated_data):
        unidades_payload = validated_data.pop("unidades", [])
        validated_data = self._clean_none(validated_data)

        try:
            livro = Livro.objects.create(**validated_data)
        except IntegrityError as e:
            raise serializers.ValidationError(self._friendly_integrity_message(e))

        if unidades_payload:
            bulk = []
            for u in unidades_payload:
                bulk.append(
                    LivroUnidade(
                        livro=livro,
                        unidade=u["unidade"],  # instância de Unidade
                        exemplares=u.get("exemplares", 1),
                    )
                )
            try:
                # se houver unique(livro,unidade), ignore_conflicts evita 500
                LivroUnidade.objects.bulk_create(bulk, ignore_conflicts=True)
            except IntegrityError as e:
                raise serializers.ValidationError({"unidades": self._friendly_integrity_message(e)})

        return livro

    @transaction.atomic
    def update(self, instance, validated_data):
        # Só sincroniza unidades se o campo vier no payload; caso contrário, mantém como está
        unidades_payload = validated_data.pop("unidades", None)
        validated_data = self._clean_none(validated_data)

        if unidades_payload is not None:
            self._validate_unidades_against_open_loans(instance, unidades_payload)

        try:
            instance = super().update(instance, validated_data)
        except IntegrityError as e:
            raise serializers.ValidationError(self._friendly_integrity_message(e))

        if unidades_payload is not None:
            # limpa vínculos antigos e recria
            LivroUnidade.objects.filter(livro=instance).delete()

            if unidades_payload:
                bulk = []
                for u in unidades_payload:
                    bulk.append(
                        LivroUnidade(
                            livro=instance,
                            unidade=u["unidade"],  # instância de Unidade
                            exemplares=u.get("exemplares", 1),
                        )
                    )
                try:
                    LivroUnidade.objects.bulk_create(bulk, ignore_conflicts=True)
                except IntegrityError as e:
                    raise serializers.ValidationError({"unidades": self._friendly_integrity_message(e)})

        return instance
