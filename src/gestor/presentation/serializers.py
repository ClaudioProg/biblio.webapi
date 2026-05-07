# 📄 src/gestor/presentation/serializers.py
from django.db import IntegrityError, transaction
from rest_framework import serializers

from gestor.domain.entities.livro import Livro
from gestor.domain.entities.unidade import Unidade
from gestor.domain.entities.livro_unidade import LivroUnidade
from gestor.domain.entities.tipo_obra import TipoObra
from gestor.domain.entities.genero import Genero  # necessário porque o Livro usa "genero" (FK)
from gestor.domain.entities.usuario import Usuario


# ============== Unidades ==============
class UnidadeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unidade
        fields = ["id", "nome", "endereco", "telefone", "email", "site"]


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ["id", "nome", "email", "telefone", "documento", "ativo", "observacoes"]


# ============== LivroUnidade (write / read) ==============
class LivroUnidadeWriteSerializer(serializers.ModelSerializer):
    # recebe ID de unidade
    unidade = serializers.PrimaryKeyRelatedField(queryset=Unidade.objects.all())

    class Meta:
        model = LivroUnidade
        fields = ["unidade", "exemplares"]


class LivroUnidadeReadSerializer(serializers.ModelSerializer):
    # devolve dados da unidade
    unidade = UnidadeSerializer(read_only=True)

    class Meta:
        model = LivroUnidade
        fields = ["unidade", "exemplares"]


# HÍBRIDO para manter compatibilidade com LivroUnidadeViewSet (read + write)
class LivroUnidadeSerializer(LivroUnidadeWriteSerializer):
    """
    - Na escrita (create/update), usa PrimaryKeyRelatedField (como Write).
    - Na leitura (response), serializa como Read (com Unidade detalhada).
    """
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
