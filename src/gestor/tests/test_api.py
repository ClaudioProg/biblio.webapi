import base64
from unittest.mock import patch

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

    def test_territory_analytics_returns_70_neighborhoods(self):
        response = self.client.get("/gestor/analytics/territorio/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["cobertura"]["bairros_total"], 70)
        self.assertEqual(response.data["cobertura"]["bairros_com_renda"], 55)
        self.assertEqual(response.data["cobertura"]["bairros_sem_renda"], 15)
        self.assertFalse(response.data["meta"]["contem_dados_pessoais"])
        self.assertEqual(len(response.data["bairros"]), 70)

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

    def test_territory_analytics_preserves_missing_income_as_null(self):
        response = self.client.get(
            "/gestor/analytics/territorio/?codigo=3548500031"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["bairros"]), 1)
        bairro = response.data["bairros"][0]
        self.assertEqual(bairro["bairro"], "Porto Valongo")
        self.assertFalse(bairro["renda_disponivel"])
        self.assertIsNone(bairro["renda_responsavel_media"])
        self.assertIsNone(bairro["renda_responsavel_mediana"])

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
        self.assertEqual(len(response.data["dim_bairro"]), 70)

        unidade = response.data["dim_unidade"][0]
        self.assertEqual(unidade["ibge_bairro_codigo"], "3548500005")
        self.assertEqual(unidade["ibge_bairro_nome"], "Aparecida")

        acervo = response.data["fato_acervo"][0]
        self.assertEqual(acervo["unidade_id"], self.unidade_a.id)
        self.assertEqual(acervo["exemplares"], 2)

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
        self.assertEqual(len(response.data["dim_bairro"]), 70)

    @patch("gestor.presentation.views.TranslationService.translate_book_payload")
    @patch("gestor.presentation.views.OpenLibraryLookupService.lookup")
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
