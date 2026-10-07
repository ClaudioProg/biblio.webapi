from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from gestor.domain.entities.genero import Genero
from gestor.domain.entities.tipo_obra import TipoObra
from gestor.domain.entities.unidade import Unidade
from gestor.domain.entities.livro import Livro
from gestor.domain.entities.livro_unidade import LivroUnidade
from gestor.domain.entities.usuario import Usuario
from gestor.domain.entities.emprestimo import Emprestimo


class GestorApiRegressionTests(APITestCase):
    def setUp(self):
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

    def test_login_rejects_invalid_credentials(self):
        public_client = APIClient()
        response = public_client.post(
            "/gestor/auth/login/",
            {"username": "gestor_teste", "password": "senha-errada"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_logout_invalidates_token(self):
        response = self.client.post("/gestor/auth/logout/", {}, format="json")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Token.objects.filter(key=self.token.key).exists())

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

    def test_database_debug_endpoint_is_not_exposed(self):
        response = self.client.get("/gestor/debug/db-info/")
        self.assertEqual(response.status_code, 404)
