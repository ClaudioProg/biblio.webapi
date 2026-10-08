import base64
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.contrib.auth.models import Group
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from gestor.domain.entities.genero import Genero
from gestor.domain.entities.tipo_obra import TipoObra
from gestor.domain.entities.unidade import Unidade
from gestor.domain.entities.livro import Livro
from gestor.domain.entities.livro_unidade import LivroUnidade
from gestor.domain.entities.usuario import Usuario
from gestor.domain.entities.emprestimo import Emprestimo
from gestor.infrastructure.external_book_services import (
    BookMetadataLookupService,
    BrasilApiLookupService,
    GoogleBooksLookupService,
    IsbnNotFoundError,
    isbn_equivalents,
)


class GestorApiRegressionTests(APITestCase):
    def setUp(self):
        # A produção possui um catálogo inicial versionado. Os testes de API
        # precisam permanecer isolados e não depender da quantidade de dados
        # carregada pela migração de homologação.
        Emprestimo.objects.all().delete()
        LivroUnidade.objects.all().delete()
        Livro.objects.all().delete()
        Unidade.objects.all().delete()
        Usuario.objects.all().delete()

        self.auth_user = get_user_model().objects.create_user(
            username="gestor_teste",
            password="SenhaForte123!",
            first_name="Gestor",
            last_name="Teste",
            is_staff=True,
        )
        self.token = Token.objects.create(user=self.auth_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        self.genero = Genero.objects.create(nome="Ficção de teste")
        self.tipo = TipoObra.objects.create(nome="Livro de teste")
        self.unidade_a = Unidade.objects.create(
            nome="Unidade A",
            endereco="Rua A, 1",
        )
        self.unidade_b = Unidade.objects.create(
            nome="Unidade B",
            endereco="Rua B, 2",
        )

    def _livro(self, isbn="9780000000001", exemplares=1):
        livro = Livro.objects.create(
            titulo="Livro Teste",
            autor="Autor Teste",
            isbn=isbn,
            genero=self.genero,
            tipo_obra=self.tipo,
        )
        LivroUnidade.objects.create(
            livro=livro,
            unidade=self.unidade_a,
            exemplares=exemplares,
        )
        return livro

    def _usuario(self, suffix="1"):
        return Usuario.objects.create(
            nome=f"Usuário {suffix}",
            email=f"usuario{suffix}@example.com",
            ativo=True,
        )

    def test_private_endpoints_require_authentication(self):
        public_client = APIClient()
        response = public_client.get("/gestor/usuarios/")
        self.assertEqual(response.status_code, 401)

    def test_login_returns_real_api_token(self):
        public_client = APIClient()
        response = public_client.post(
            "/gestor/auth/login/",
            {"username": "gestor_teste", "password": "SenhaForte123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["token"], self.token.key)
        self.assertEqual(response.data["user"]["username"], "gestor_teste")
        self.assertEqual(response.data["user"]["role"], "staff")

    def test_login_reuses_single_existing_token(self):
        public_client = APIClient()

        first = public_client.post(
            "/gestor/auth/login/",
            {"username": "gestor_teste", "password": "SenhaForte123!"},
            format="json",
        )
        second = public_client.post(
            "/gestor/auth/login/",
            {"username": "gestor_teste", "password": "SenhaForte123!"},
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["token"], second.data["token"])
        self.assertEqual(
            Token.objects.filter(user=self.auth_user).count(),
            1,
        )

    def test_login_recreates_token_after_password_reset_deleted_previous_token(self):
        old_key = self.token.key
        self.token.delete()
        self.assertFalse(
            Token.objects.filter(user=self.auth_user).exists()
        )

        public_client = APIClient()
        response = public_client.post(
            "/gestor/auth/login/",
            {"username": "gestor_teste", "password": "SenhaForte123!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["token"])
        self.assertNotEqual(response.data["token"], old_key)
        self.assertEqual(
            Token.objects.filter(user=self.auth_user).count(),
            1,
        )

    def test_login_rejects_invalid_credentials(self):
        public_client = APIClient()
        response = public_client.post(
            "/gestor/auth/login/",
            {"username": "gestor_teste", "password": "senha-errada"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_nonstaff_account_cannot_login_to_management(self):
        reader = get_user_model().objects.create_user(
            username="powerbi_only",
            password="PowerBI123!Seguro",
            is_staff=False,
        )
        group, _ = Group.objects.get_or_create(name="powerbi_reader")
        reader.groups.add(group)

        public_client = APIClient()
        response = public_client.post(
            "/gestor/auth/login/",
            {"username": "powerbi_only", "password": "PowerBI123!Seguro"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Token.objects.filter(user=reader).exists())

    def test_powerbi_reader_group_can_use_basic_auth_only_for_dataset(self):
        reader = get_user_model().objects.create_user(
            username="powerbi_reader_test",
            password="PowerBI123!Seguro",
            is_staff=False,
        )
        group, _ = Group.objects.get_or_create(name="powerbi_reader")
        reader.groups.add(group)

        credentials = base64.b64encode(
            b"powerbi_reader_test:PowerBI123!Seguro"
        ).decode("ascii")
        public_client = APIClient()

        dataset = public_client.get(
            "/gestor/analytics/powerbi/",
            HTTP_AUTHORIZATION=f"Basic {credentials}",
        )
        users = public_client.get(
            "/gestor/usuarios/",
            HTTP_AUTHORIZATION=f"Basic {credentials}",
        )

        self.assertEqual(dataset.status_code, 200)
        self.assertFalse(dataset.data["meta"]["contem_dados_pessoais"])
        self.assertEqual(users.status_code, 401)

    def test_nonstaff_basic_account_without_powerbi_group_is_forbidden(self):
        get_user_model().objects.create_user(
            username="basic_sem_grupo",
            password="PowerBI123!Seguro",
            is_staff=False,
        )
        credentials = base64.b64encode(
            b"basic_sem_grupo:PowerBI123!Seguro"
        ).decode("ascii")

        response = APIClient().get(
            "/gestor/analytics/powerbi/",
            HTTP_AUTHORIZATION=f"Basic {credentials}",
        )

        self.assertEqual(response.status_code, 403)

    def test_logout_invalidates_token(self):
        response = self.client.post("/gestor/auth/logout/", {}, format="json")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Token.objects.filter(key=self.token.key).exists())

    def test_authenticated_user_can_change_password(self):
        response = self.client.post(
            "/gestor/auth/change-password/",
            {
                "current_password": "SenhaForte123!",
                "new_password": "NovaSenhaForte456!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get("token"))
        self.auth_user.refresh_from_db()
        self.assertTrue(self.auth_user.check_password("NovaSenhaForte456!"))
        self.assertFalse(Token.objects.filter(key=self.token.key).exists())

    def test_change_password_rejects_wrong_current_password(self):
        response = self.client.post(
            "/gestor/auth/change-password/",
            {
                "current_password": "senha-errada",
                "new_password": "NovaSenhaForte456!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("current_password", response.data)

    def test_staff_cannot_manage_platform_access_accounts(self):
        response = self.client.get("/gestor/acessos/")
        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_staff_access_account_and_new_account_can_login(self):
        self.auth_user.is_superuser = True
        self.auth_user.save(update_fields=["is_superuser"])

        create = self.client.post(
            "/gestor/acessos/",
            {
                "username": "bibliotecaria_teste",
                "first_name": "Bibliotecária",
                "last_name": "Teste",
                "email": "bibliotecaria@example.com",
                "role": "staff",
                "active": True,
                "password": "SenhaTemporaria789!",
            },
            format="json",
        )

        self.assertEqual(create.status_code, 201)
        self.assertNotIn("password", create.data)
        self.assertEqual(create.data["role"], "staff")
        self.assertTrue(create.data["active"])

        login = APIClient().post(
            "/gestor/auth/login/",
            {
                "username": "bibliotecaria_teste",
                "password": "SenhaTemporaria789!",
            },
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data["user"]["role"], "staff")

    def test_admin_cannot_deactivate_own_account(self):
        self.auth_user.is_superuser = True
        self.auth_user.save(update_fields=["is_superuser"])

        response = self.client.patch(
            f"/gestor/acessos/{self.auth_user.id}/",
            {"active": False},
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.auth_user.refresh_from_db()
        self.assertTrue(self.auth_user.is_active)
        self.assertTrue(self.auth_user.is_superuser)

    def test_last_admin_cannot_be_demoted(self):
        self.auth_user.is_superuser = True
        self.auth_user.save(update_fields=["is_superuser"])

        response = self.client.patch(
            f"/gestor/acessos/{self.auth_user.id}/",
            {"role": "staff"},
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.auth_user.refresh_from_db()
        self.assertTrue(self.auth_user.is_superuser)

    def test_admin_can_reset_staff_password_and_invalidates_old_token(self):
        self.auth_user.is_superuser = True
        self.auth_user.save(update_fields=["is_superuser"])
        User = get_user_model()
        staff = User.objects.create_user(
            username="operador_reset",
            password="SenhaAnterior789!",
            is_staff=True,
        )
        old_token = Token.objects.create(user=staff)

        response = self.client.post(
            f"/gestor/acessos/{staff.id}/reset-password/",
            {"password": "SenhaNova789!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Token.objects.filter(key=old_token.key).exists())

        login = APIClient().post(
            "/gestor/auth/login/",
            {
                "username": "operador_reset",
                "password": "SenhaNova789!",
            },
            format="json",
        )
        self.assertEqual(login.status_code, 200)

    def test_access_accounts_are_deactivated_not_deleted(self):
        self.auth_user.is_superuser = True
        self.auth_user.save(update_fields=["is_superuser"])
        staff = get_user_model().objects.create_user(
            username="operador_preservado",
            password="SenhaValida789!",
            is_staff=True,
        )

        response = self.client.delete(f"/gestor/acessos/{staff.id}/")

        self.assertEqual(response.status_code, 405)
        self.assertTrue(get_user_model().objects.filter(pk=staff.id).exists())

    def test_unidade_crud_persists_through_api(self):
        create = self.client.post(
            "/gestor/unidades/",
            {
                "nome": "Unidade C",
                "endereco": "Rua C, 3",
                "telefone": "",
                "email": "",
                "site": "",
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        unidade_id = create.data["id"]

        update = self.client.put(
            f"/gestor/unidades/{unidade_id}/",
            {
                "nome": "Unidade C Atualizada",
                "endereco": "Rua C, 30",
                "telefone": "",
                "email": "",
                "site": "",
            },
            format="json",
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.data["nome"], "Unidade C Atualizada")

        delete = self.client.delete(f"/gestor/unidades/{unidade_id}/")
        self.assertEqual(delete.status_code, 204)
        self.assertFalse(Unidade.objects.filter(pk=unidade_id).exists())

    def test_unidade_accepts_valid_ibge_neighborhood_and_exposes_name(self):
        response = self.client.post(
            "/gestor/unidades/",
            {
                "nome": "Biblioteca territorial",
                "endereco": "Avenida de teste",
                "telefone": "",
                "email": "",
                "site": "",
                "ibge_bairro_codigo": "3548500005",
                "latitude": "-23.979587",
                "longitude": "-46.314403",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["ibge_bairro_codigo"], "3548500005")
        self.assertEqual(response.data["ibge_bairro_nome"], "Aparecida")
        self.assertEqual(str(response.data["latitude"]), "-23.979587")
        self.assertEqual(str(response.data["longitude"]), "-46.314403")

    def test_unidade_rejects_unknown_ibge_neighborhood_code(self):
        response = self.client.post(
            "/gestor/unidades/",
            {
                "nome": "Biblioteca inválida",
                "endereco": "Avenida de teste",
                "ibge_bairro_codigo": "9999999999",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("ibge_bairro_codigo", response.data)

    def test_livro_list_avoids_n_plus_one_queries(self):
        for index in range(20):
            livro = Livro.objects.create(
                titulo=f"Livro performance {index}",
                autor="Autor",
                isbn=f"9781234567{index:03d}",
                genero=self.genero,
                tipo_obra=self.tipo,
            )
            LivroUnidade.objects.create(
                livro=livro,
                unidade=self.unidade_a,
                exemplares=2,
            )
            LivroUnidade.objects.create(
                livro=livro,
                unidade=self.unidade_b,
                exemplares=1,
            )

        usuario = self._usuario("perf")
        primeiro_livro = Livro.objects.order_by("id").first()
        Emprestimo.objects.create(
            livro=primeiro_livro,
            unidade=self.unidade_a,
            usuario=usuario,
            data_emprestimo="2026-05-18",
            status=Emprestimo.STATUS_ABERTO,
        )

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get("/gestor/livros/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 20)
        self.assertLessEqual(
            len(captured),
            8,
            f"Lista executou {len(captured)} queries; possível regressão N+1.",
        )

        first = response.data[0]
        unidade_a = next(
            item
            for item in first["unidades_detalhe"]
            if item["unidade"]["id"] == self.unidade_a.id
        )
        self.assertEqual(unidade_a["emprestimos_abertos"], 1)
        self.assertEqual(unidade_a["exemplares_disponiveis"], 1)

    def test_livro_create_persists_unidades_and_exemplares(self):
        response = self.client.post(
            "/gestor/livros/",
            {
                "titulo": "Livro com unidades",
                "autor": "Autora",
                "isbn": "9780000000002",
                "genero": self.genero.id,
                "tipo_obra": self.tipo.id,
                "unidades": [
                    {"unidade": self.unidade_a.id, "exemplares": 2},
                    {"unidade": self.unidade_b.id, "exemplares": 3},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data["unidades_detalhe"]), 2)
        livro_id = response.data["id"]

        relacoes = LivroUnidade.objects.filter(livro_id=livro_id).order_by(
            "unidade_id"
        )
        self.assertEqual(relacoes.count(), 2)
        self.assertEqual(
            sorted(relacoes.values_list("exemplares", flat=True)),
            [2, 3],
        )

    def test_livro_patch_replaces_unidades(self):
        livro = self._livro(isbn="9780000000003", exemplares=2)

        response = self.client.patch(
            f"/gestor/livros/{livro.id}/",
            {
                "unidades": [
                    {"unidade": self.unidade_b.id, "exemplares": 4},
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        relacoes = list(LivroUnidade.objects.filter(livro=livro))
        self.assertEqual(len(relacoes), 1)
        self.assertEqual(relacoes[0].unidade_id, self.unidade_b.id)
        self.assertEqual(relacoes[0].exemplares, 4)

    def test_emprestimo_blocks_overbooking(self):
        livro = self._livro(isbn="9780000000004", exemplares=1)
        usuario_a = self._usuario("a")
        usuario_b = self._usuario("b")

        primeiro = self.client.post(
            "/gestor/emprestimos/",
            {
                "livro": livro.id,
                "unidade": self.unidade_a.id,
                "usuario": usuario_a.id,
                "data_emprestimo": "2026-05-18",
                "data_prevista_devolucao": "2026-06-01",
                "status": "aberto",
            },
            format="json",
        )
        self.assertEqual(primeiro.status_code, 201)

        segundo = self.client.post(
            "/gestor/emprestimos/",
            {
                "livro": livro.id,
                "unidade": self.unidade_a.id,
                "usuario": usuario_b.id,
                "data_emprestimo": "2026-05-18",
                "data_prevista_devolucao": "2026-06-01",
                "status": "aberto",
            },
            format="json",
        )
        self.assertEqual(segundo.status_code, 400)
        self.assertEqual(
            Emprestimo.objects.filter(
                livro=livro,
                unidade=self.unidade_a,
                status=Emprestimo.STATUS_ABERTO,
            ).count(),
            1,
        )

    def test_loan_create_uses_row_lock_for_stock_capacity(self):
        livro = self._livro(isbn="9780000000015", exemplares=1)
        usuario = self._usuario("lock")

        with patch.object(
            LivroUnidade.objects,
            "select_for_update",
            wraps=LivroUnidade.objects.select_for_update,
        ) as lock_mock:
            response = self.client.post(
                "/gestor/emprestimos/",
                {
                    "livro": livro.id,
                    "unidade": self.unidade_a.id,
                    "usuario": usuario.id,
                    "data_emprestimo": "2026-05-18",
                    "status": "aberto",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(lock_mock.called)

    def test_returned_loan_cannot_reopen_when_last_copy_is_occupied(self):
        livro = self._livro(isbn="9780000000016", exemplares=1)
        usuario_a = self._usuario("reopen-a")
        usuario_b = self._usuario("reopen-b")

        Emprestimo.objects.create(
            livro=livro,
            unidade=self.unidade_a,
            usuario=usuario_a,
            data_emprestimo="2026-05-01",
            data_devolucao="2026-05-10",
            status=Emprestimo.STATUS_DEVOLVIDO,
        )
        aberto = Emprestimo.objects.create(
            livro=livro,
            unidade=self.unidade_a,
            usuario=usuario_b,
            data_emprestimo="2026-05-18",
            status=Emprestimo.STATUS_ABERTO,
        )
        devolvido = Emprestimo.objects.get(usuario=usuario_a)

        response = self.client.patch(
            f"/gestor/emprestimos/{devolvido.id}/",
            {
                "status": Emprestimo.STATUS_ABERTO,
                "data_devolucao": None,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        devolvido.refresh_from_db()
        aberto.refresh_from_db()
        self.assertEqual(devolvido.status, Emprestimo.STATUS_DEVOLVIDO)
        self.assertEqual(aberto.status, Emprestimo.STATUS_ABERTO)

    def test_devolucao_requires_date(self):
        livro = self._livro(isbn="9780000000005", exemplares=1)
        usuario = self._usuario("c")
        emprestimo = Emprestimo.objects.create(
            livro=livro,
            unidade=self.unidade_a,
            usuario=usuario,
            data_emprestimo="2026-05-18",
            data_prevista_devolucao="2026-06-01",
            status=Emprestimo.STATUS_ABERTO,
        )

        response = self.client.patch(
            f"/gestor/emprestimos/{emprestimo.id}/",
            {"status": Emprestimo.STATUS_DEVOLVIDO},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("data_devolucao", response.data)

    def test_entities_with_loan_history_cannot_be_deleted(self):
        livro = self._livro(isbn="9780000000006", exemplares=1)
        usuario = self._usuario("d")
        emprestimo = Emprestimo.objects.create(
            livro=livro,
            unidade=self.unidade_a,
            usuario=usuario,
            data_emprestimo="2026-05-18",
            data_prevista_devolucao="2026-06-01",
            status=Emprestimo.STATUS_ABERTO,
        )

        for endpoint in (
            f"/gestor/livros/{livro.id}/",
            f"/gestor/unidades/{self.unidade_a.id}/",
            f"/gestor/usuarios/{usuario.id}/",
        ):
            response = self.client.delete(endpoint)
            self.assertEqual(response.status_code, 409)

        self.assertTrue(Livro.objects.filter(pk=livro.id).exists())
        self.assertTrue(Unidade.objects.filter(pk=self.unidade_a.id).exists())
        self.assertTrue(Usuario.objects.filter(pk=usuario.id).exists())
        self.assertTrue(Emprestimo.objects.filter(pk=emprestimo.id).exists())

    def test_emprestimo_history_cannot_be_hard_deleted(self):
        livro = self._livro(isbn="9780000000007", exemplares=1)
        usuario = self._usuario("e")
        emprestimo = Emprestimo.objects.create(
            livro=livro,
            unidade=self.unidade_a,
            usuario=usuario,
            data_emprestimo="2026-05-18",
            status=Emprestimo.STATUS_ABERTO,
        )

        response = self.client.delete(f"/gestor/emprestimos/{emprestimo.id}/")
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Emprestimo.objects.filter(pk=emprestimo.id).exists())

    def test_stock_cannot_be_reduced_below_open_loans(self):
        livro = self._livro(isbn="9780000000008", exemplares=1)
        usuario = self._usuario("f")
        Emprestimo.objects.create(
            livro=livro,
            unidade=self.unidade_a,
            usuario=usuario,
            data_emprestimo="2026-05-18",
            status=Emprestimo.STATUS_ABERTO,
        )

        response = self.client.patch(
            f"/gestor/livros/{livro.id}/",
            {"unidades": []},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            LivroUnidade.objects.get(livro=livro, unidade=self.unidade_a).exemplares,
            1,
        )

    def test_book_library_link_cannot_be_removed_with_open_loan(self):
        livro = self._livro(isbn="9780000000009", exemplares=1)
        usuario = self._usuario("g")
        Emprestimo.objects.create(
            livro=livro,
            unidade=self.unidade_a,
            usuario=usuario,
            data_emprestimo="2026-05-18",
            status=Emprestimo.STATUS_ABERTO,
        )
        relation = LivroUnidade.objects.get(
            livro=livro,
            unidade=self.unidade_a,
        )

        response = self.client.delete(
            f"/gestor/livro-unidades/{relation.id}/"
        )
        self.assertEqual(response.status_code, 409)
        self.assertTrue(LivroUnidade.objects.filter(pk=relation.id).exists())

    def test_new_loan_rejects_inactive_user(self):
        livro = self._livro(isbn="9780000000010", exemplares=1)
        usuario = self._usuario("h")
        usuario.ativo = False
        usuario.save(update_fields=["ativo"])

        response = self.client.post(
            "/gestor/emprestimos/",
            {
                "livro": livro.id,
                "unidade": self.unidade_a.id,
                "usuario": usuario.id,
                "data_emprestimo": "2026-05-18",
                "status": "aberto",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("usuario", response.data)

    def test_book_detail_exposes_current_availability(self):
        livro = self._livro(isbn="9780000000011", exemplares=2)
        usuario = self._usuario("i")
        Emprestimo.objects.create(
            livro=livro,
            unidade=self.unidade_a,
            usuario=usuario,
            data_emprestimo="2026-05-18",
            status=Emprestimo.STATUS_ABERTO,
        )

        response = self.client.get(f"/gestor/livros/{livro.id}/")

        self.assertEqual(response.status_code, 200)
        detalhe = response.data["unidades_detalhe"][0]
        self.assertEqual(detalhe["exemplares"], 2)
        self.assertEqual(detalhe["emprestimos_abertos"], 1)
        self.assertEqual(detalhe["exemplares_disponiveis"], 1)

    def test_analytics_summary_is_aggregated_and_contains_no_personal_data(self):
        livro = self._livro(isbn="9780000000012", exemplares=3)
        usuario = self._usuario("j")
        Emprestimo.objects.create(
            livro=livro,
            unidade=self.unidade_a,
            usuario=usuario,
            data_emprestimo="2026-05-18",
            status=Emprestimo.STATUS_ABERTO,
        )

        response = self.client.get("/gestor/analytics/resumo/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["meta"]["contém_dados_pessoais"])
        self.assertEqual(response.data["resumo"]["titulos"], 1)
        self.assertEqual(response.data["resumo"]["exemplares"], 3)
        self.assertEqual(response.data["resumo"]["emprestimos_abertos"], 1)
        self.assertEqual(response.data["acervo_por_genero"][0]["genero"], self.genero.nome)
        self.assertEqual(response.data["por_unidade"][0]["unidade"], self.unidade_a.nome)

        serialized = str(response.data)
        self.assertNotIn(usuario.email, serialized)
        if usuario.documento:
            self.assertNotIn(usuario.documento, serialized)

    def test_analytics_summary_links_unit_to_ibge_neighborhood(self):
        self.unidade_a.ibge_bairro_codigo = "3548500005"
        self.unidade_a.latitude = "-23.979587"
        self.unidade_a.longitude = "-46.314403"
        self.unidade_a.save(
            update_fields=["ibge_bairro_codigo", "latitude", "longitude"]
        )
        self._livro(isbn="9780000000013", exemplares=2)

        response = self.client.get("/gestor/analytics/resumo/")

        self.assertEqual(response.status_code, 200)
        unidade = response.data["por_unidade"][0]
        self.assertEqual(unidade["ibge_bairro_codigo"], "3548500005")
        self.assertEqual(unidade["ibge_bairro_nome"], "Aparecida")
        self.assertEqual(str(unidade["latitude"]), "-23.979587")
        self.assertEqual(str(unidade["longitude"]), "-46.314403")

    def test_analytics_requires_authentication(self):
        public_client = APIClient()
        response = public_client.get("/gestor/analytics/resumo/")
        self.assertEqual(response.status_code, 401)

    def test_territory_analytics_returns_55_confirmed_neighborhoods(self):
        response = self.client.get("/gestor/analytics/territorio/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["cobertura"]["bairros_total"], 55)
        self.assertEqual(response.data["cobertura"]["bairros_com_renda"], 55)
        self.assertEqual(response.data["cobertura"]["bairros_sem_renda"], 0)
        self.assertFalse(response.data["meta"]["contem_dados_pessoais"])
        self.assertEqual(len(response.data["bairros"]), 55)

    def test_territory_analytics_can_filter_paqueta_by_code(self):
        response = self.client.get(
            "/gestor/analytics/territorio/?codigo=3548500016"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["bairros"]), 1)
        bairro = response.data["bairros"][0]
        self.assertEqual(bairro["bairro"], "Paquetá")
        self.assertEqual(bairro["cd_bairro"], "3548500016")
        self.assertTrue(bairro["renda_disponivel"])

    def test_territory_analytics_excludes_unconfirmed_neighborhood(self):
        response = self.client.get(
            "/gestor/analytics/territorio/?codigo=3548500031"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["bairros"], [])

    def test_territory_analytics_requires_authentication(self):
        public_client = APIClient()
        response = public_client.get("/gestor/analytics/territorio/")
        self.assertEqual(response.status_code, 401)

    def test_powerbi_dataset_is_normalized_and_contains_no_reader_pii(self):
        self.unidade_a.ibge_bairro_codigo = "3548500005"
        self.unidade_a.latitude = "-23.979587"
        self.unidade_a.longitude = "-46.314403"
        self.unidade_a.save(
            update_fields=["ibge_bairro_codigo", "latitude", "longitude"]
        )
        livro = self._livro(isbn="9780000000014", exemplares=2)
        usuario = self._usuario("powerbi")
        usuario.documento = "12345678900"
        usuario.save(update_fields=["documento"])

        Emprestimo.objects.create(
            livro=livro,
            unidade=self.unidade_a,
            usuario=usuario,
            data_emprestimo="2026-05-18",
            status=Emprestimo.STATUS_ABERTO,
        )
        Emprestimo.objects.create(
            livro=livro,
            unidade=self.unidade_a,
            usuario=usuario,
            data_emprestimo="2026-06-02",
            data_devolucao="2026-06-10",
            status=Emprestimo.STATUS_DEVOLVIDO,
        )

        response = self.client.get("/gestor/analytics/powerbi/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["meta"]["contem_dados_pessoais"])
        self.assertEqual(len(response.data["dim_bairro"]), 55)

        unidade = response.data["dim_unidade"][0]
        self.assertEqual(unidade["ibge_bairro_codigo"], "3548500005")
        self.assertEqual(unidade["ibge_bairro_nome"], "Aparecida")

        acervo = response.data["fato_acervo"][0]
        self.assertEqual(acervo["unidade_id"], self.unidade_a.id)
        self.assertEqual(acervo["exemplares"], 2)
        self.assertEqual(acervo["emprestimos_abertos"], 1)
        self.assertEqual(acervo["exemplares_disponiveis"], 1)

        meses = {
            row["mes"]: row["emprestimos_iniciados"]
            for row in response.data["fato_circulacao_mensal"]
        }
        self.assertEqual(meses["2026-05-01"], 1)
        self.assertEqual(meses["2026-06-01"], 1)

        devolucoes = {
            row["mes"]: row["devolucoes"]
            for row in response.data["fato_devolucoes_mensal"]
        }
        self.assertEqual(devolucoes["2026-06-01"], 1)

        titulo = response.data["fato_titulos"][0]
        self.assertEqual(titulo["emprestimos_total"], 2)
        self.assertEqual(titulo["emprestimos_abertos"], 1)
        self.assertEqual(titulo["exemplares_disponiveis"], 1)

        serialized = str(response.data)
        self.assertNotIn(usuario.email, serialized)
        self.assertNotIn(usuario.documento, serialized)

    def test_powerbi_dataset_requires_authentication(self):
        public_client = APIClient()
        response = public_client.get("/gestor/analytics/powerbi/")
        self.assertEqual(response.status_code, 401)

    def test_powerbi_dataset_accepts_http_basic_auth(self):
        public_client = APIClient()
        credentials = base64.b64encode(
            b"gestor_teste:SenhaForte123!"
        ).decode("ascii")
        response = public_client.get(
            "/gestor/analytics/powerbi/",
            HTTP_AUTHORIZATION=f"Basic {credentials}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["meta"]["contem_dados_pessoais"])
        self.assertEqual(len(response.data["dim_bairro"]), 55)

    def test_isbn_equivalents_convert_between_isbn10_and_isbn13(self):
        self.assertEqual(
            isbn_equivalents("8587600826"),
            {"8587600826", "9788587600820"},
        )
        self.assertEqual(
            isbn_equivalents("9788587600820"),
            {"8587600826", "9788587600820"},
        )

    def test_brasilapi_maps_fundamentos_em_infectologia(self):
        service = BrasilApiLookupService()
        payload = service._map_to_payload(
            "9788587600820",
            {
                "isbn": "8587600826",
                "title": "FUNDAMENTOS EM INFECTOLOGIA",
                "authors": [
                    "ENIO ROBERTO PIETRA PEDROSO",
                    "MANOEL OTÁVIO DA COSTA ROCHA",
                ],
                "publisher": "RUBIO",
                "year": None,
                "page_count": None,
                "cover_url": None,
                "provider": "cbl",
            },
        )

        self.assertEqual(payload["titulo"], "FUNDAMENTOS EM INFECTOLOGIA")
        self.assertEqual(payload["editora"], "RUBIO")
        self.assertIn("ENIO ROBERTO PIETRA PEDROSO", payload["autor"])
        self.assertEqual(payload["source"], "brasilapi:cbl")

    def test_brasilapi_accepts_equivalent_isbn10_response(self):
        service = BrasilApiLookupService()
        self.assertTrue(
            service._matches_requested_isbn(
                "9788587600820",
                {"isbn": "8587600826"},
            )
        )

    def test_brasilapi_maps_etnografias_even_without_authors(self):
        service = BrasilApiLookupService()
        payload = service._map_to_payload(
            "9788576173755",
            {
                "isbn": "9788576173755",
                "title": "Etnografias em serviços de saúde",
                "authors": [],
                "publisher": "Garamond",
                "year": None,
                "page_count": None,
                "provider": "cbl",
            },
        )
        self.assertEqual(payload["titulo"], "Etnografias em serviços de saúde")
        self.assertEqual(payload["autor"], "")
        self.assertEqual(payload["editora"], "Garamond")
        self.assertEqual(payload["source"], "brasilapi:cbl")

    def test_google_books_requires_exact_identifier_match(self):
        service = GoogleBooksLookupService()
        item = {
            "volumeInfo": {
                "title": "Fundamentos em Infectologia",
                "authors": [
                    "Manoel Otávio da Costa Rocha",
                    "Enio Roberto Pietra Pedroso",
                ],
                "publisher": "Rubio",
                "publishedDate": "2009",
                "pageCount": 1120,
                "language": "pt",
                "industryIdentifiers": [
                    {"type": "ISBN_10", "identifier": "8587600826"},
                    {"type": "ISBN_13", "identifier": "9788587600820"},
                ],
            }
        }

        found = service._find_exact_item(
            "9788587600820",
            {"items": [item]},
        )
        self.assertEqual(found, item)

    def test_google_books_maps_real_fallback_payload(self):
        service = GoogleBooksLookupService()
        item = {
            "volumeInfo": {
                "title": "Etnografias em Serviços de Saúde",
                "authors": ["Jaqueline Ferreira", "Soraya Fleischer"],
                "publisher": "Garamond",
                "publishedDate": "2014",
                "pageCount": 360,
                "language": "pt",
                "industryIdentifiers": [
                    {"type": "ISBN_13", "identifier": "9788576173755"},
                ],
            }
        }

        payload = service._map_to_payload("9788576173755", item)
        self.assertEqual(payload["titulo"], "Etnografias em Serviços de Saúde")
        self.assertEqual(payload["autor"], "Jaqueline Ferreira, Soraya Fleischer")
        self.assertEqual(payload["editora"], "Garamond")
        self.assertEqual(payload["data_publicacao"], "2014-01-01")
        self.assertEqual(payload["paginas"], 360)
        self.assertEqual(payload["idioma"], "Portuguese")
        self.assertEqual(payload["source"], "googlebooks")

    def test_book_metadata_lookup_falls_back_after_openlibrary_miss(self):
        service = BookMetadataLookupService()
        expected = {
            "isbn": "9788576173755",
            "titulo": "Etnografias em Serviços de Saúde",
            "autor": "Jaqueline Ferreira, Soraya Fleischer",
            "source": "googlebooks",
        }

        with patch.object(
            service.providers[0],
            "lookup",
            side_effect=IsbnNotFoundError("não encontrado"),
        ), patch.object(
            service.providers[1],
            "lookup",
            side_effect=IsbnNotFoundError("não encontrado"),
        ), patch.object(
            service.providers[2],
            "lookup",
            return_value=expected,
        ):
            result = service.lookup("9788576173755")

        self.assertEqual(result, expected)

    @patch("gestor.presentation.views.TranslationService.translate_book_payload")
    @patch("gestor.presentation.views.BookMetadataLookupService.lookup")
    def test_isbn_lookup_returns_book_metadata(
        self,
        lookup_mock,
        translate_mock,
    ):
        payload = {
            "isbn": "9780140328721",
            "titulo": "Fantastic Mr. Fox",
            "autor": "Roald Dahl",
            "editora": "Puffin",
            "data_publicacao": "1988-01-01",
            "paginas": 96,
            "capa": "https://covers.openlibrary.org/example.jpg",
            "idioma": "English",
            "source": "openlibrary",
        }
        lookup_mock.return_value = payload
        translate_mock.return_value = (
            payload,
            {
                "provider": "none",
                "translated_fields": [],
                "warnings": [],
            },
        )

        response = self.client.get(
            "/gestor/livros/isbn-lookup/?isbn=978-0-14-032872-1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["isbn"], "9780140328721")
        self.assertEqual(response.data["data"]["titulo"], "Fantastic Mr. Fox")
        self.assertEqual(response.data["data"]["autor"], "Roald Dahl")
        lookup_mock.assert_called_once_with("978-0-14-032872-1")

    def test_isbn_lookup_rejects_invalid_isbn_without_external_request(self):
        response = self.client.get(
            "/gestor/livros/isbn-lookup/?isbn=1234567890123"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("ISBN inválido", response.data["detail"])

    def test_isbn_lookup_requires_authentication(self):
        public_client = APIClient()
        response = public_client.get(
            "/gestor/livros/isbn-lookup/?isbn=9780140328721"
        )
        self.assertEqual(response.status_code, 401)

    def test_database_debug_endpoint_is_not_exposed(self):
        response = self.client.get("/gestor/debug/db-info/")
        self.assertEqual(response.status_code, 404)
