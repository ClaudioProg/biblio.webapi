# BiblioWebAPI - Sistema de Gerenciamento de Empréstimo de Livros

## Descrição

O **BiblioWebAPI** é um sistema desenvolvido para gerenciar o empréstimo de livros em bibliotecas públicas. Ele é construído usando o **Django** e segue as boas práticas de arquitetura **DDD (Domain-Driven Design)**, com uma estrutura modular e escalável. O projeto está configurado para ser extensível, facilitando a integração de novos contextos (como gestão de doações, acervo, etc.).

## Principais Características

- **Gestão de Empréstimos**: Registro de empréstimos de livros, com controle de prazo e devoluções.
- **Módulos Escaláveis**: Estrutura baseada em DDD, com separação clara entre camadas de domínio, aplicação, infraestrutura e apresentação.
- **Persistência de Dados**: Suporte a SQLite local e banco relacional via `DATABASE_URL`.
- **API REST**: Fornece endpoints para interação com os dados do sistema.
- **Facilidade de Expansão**: Novo contexto e funcionalidades podem ser facilmente adicionados sem afetar o funcionamento do sistema.
- **Segurança**: Configurações de segurança como CORS, CSRF e autenticação implementadas.

## Tecnologias Utilizadas

- **Python 3.x**
- **Django 3.x**
- **MySQL**
- **Django REST Framework** (para construção da API)
- **Gunicorn** (servidor WSGI)
- **Docker** (opcional para containerização)

## Requisitos

- Python 3.8 ou superior
- MySQL 5.7 ou superior

## Como Executar o Projeto

### 1\. **Clone o Repositório**

```bash
git clone https://github.com/JulianGN/biblio.webapi.git  cd .\biblio.webapi\
```

### 2\. **Instale as Dependências**

Recomenda-se criar um ambiente virtual antes de instalar as dependências.

```bash
python3 -m venv venv
source venv/bin/activate  # Para Linux/macOS
venv\Scripts\activate     # Para Windows
pip install -r requirements.txt
```

### 3\. **Configuração do Banco de Dados**

Se você for usar o banco publicado, configure a variável `DATABASE_URL` no arquivo `.env` com a URL de conexão remota.
Se quiser rodar localmente sem banco externo, deixe `DATABASE_URL` vazio e o projeto usará SQLite como fallback.

### Configuração de Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

```env
# DATABASE_URL=postgresql://usuario:senha@host:5432/banco
# ou deixe vazio para SQLite local
DATABASE_URL=
SECRET_KEY=sua_chave_secreta
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:5173
CORS_ALLOWED_ORIGINS=http://localhost:5173
OPENLIBRARY_BASE_URL=https://openlibrary.org
OPENLIBRARY_TIMEOUT_SECONDS=8
OPENLIBRARY_USER_AGENT=BibliotecasConectadas/1.0
OPENLIBRARY_CONTACT_EMAIL=contato@exemplo.com
ISBN_LOOKUP_CACHE_TTL_SECONDS=86400
GOOGLE_TRANSLATE_ENABLED=False
GOOGLE_TRANSLATE_API_KEY=
MYMEMORY_BASE_URL=https://api.mymemory.translated.net
MYMEMORY_CONTACT_EMAIL=contato@exemplo.com
TRANSLATION_SOURCE_LANG=auto
TRANSLATION_TARGET_LANG=pt-BR
TRANSLATION_FIELDS=titulo,idioma
```

### 4\. **Realize as Migrações**

Para configurar o banco de dados com as tabelas necessárias:

```bash
python manage.py migrate
```

### 5\. **Crie um Superusuário (opcional)**

Crie um superusuário para acessar o painel de administração do Django:

```bash
python manage.py createsuperuser
```

### 6\. **Execute o Servidor de Desenvolvimento**

Para rodar o servidor de desenvolvimento:

```bash
python manage.py runserver
```

Acesse a API em http://127.0.0.1:8000/.

### Atalho de comando único (estilo scripts)

Também é possível rodar o backend com um único comando usando o launcher local:

```bash
python run.py dev
```

Esse comando executa, em sequência:

1. `python manage.py check`
2. `python manage.py migrate`
3. `python manage.py runserver`

Outros atalhos disponíveis:

```bash
python run.py check
python run.py migrate
python run.py makemigrations
python run.py makemigrations gestor
```

### 7\. **Docker (opcional)**

Se preferir rodar o projeto em um contêiner Docker, crie a imagem com o comando:

```bash
docker-compose up --build
```

Isso iniciará o serviço em contêiner, e você poderá acessar a aplicação no localhost:8000.

## Estrutura do Projeto

```markdown
biblio.webapi/
│── src/
│ │── gestor/ # Contexto "Gestor" (Empréstimos)
│ │ │── domain/ # Entidades e regras de negócio
│ │ │── application/ # Casos de uso
│ │ │── infrastructure/ # Integração com banco, APIs externas
│ │ │── presentation/ # Controllers, Views, Serializers
│── config/ # Configurações gerais do projeto (Banco de dados, segurança)
│── manage.py # CLI do Django
│── requirements.txt # Dependências do projeto
```

## Rotas da API

A seguir estão algumas rotas da API disponíveis:

- **GET /gestor/livros/**: Listar todos os livros.
- **POST /gestor/livros/**: Criar um novo livro. Envie os seguintes campos no corpo da requisição:
  ```json
  {
    "titulo": "Título do Livro",
    "autor": "Nome do Autor",
    "genero": 1, // ID de um gênero existente
    "editora": "Nome da Editora",
    "isbn": "1234567890123",
    "paginas": 100,
    "idioma": "Português",
    "unidades": [
      { "unidade": 1, "exemplares": 5 },
      { "unidade": 2, "exemplares": 3 }
    ]
  }
  ```
- **GET /gestor/livros/{id}/**: Obter detalhes de um livro específico.
- **PUT /gestor/livros/{id}/**: Atualizar um livro específico. Envie todos os campos obrigatórios.
- **PATCH /gestor/livros/{id}/**: Atualizar parcialmente um livro específico. Envie apenas os campos que deseja alterar.
- **DELETE /gestor/livros/{id}/**: Excluir um livro específico.

- **GET /gestor/unidades/**: Listar todas as unidades.
- **POST /gestor/unidades/**: Criar uma nova unidade. Envie os seguintes campos no corpo da requisição:
  ```json
  {
    "nome": "Unidade Central",
    "endereco": "Rua Principal, 123",
    "telefone": "(11) 1234-5678",
    "email": "contato@unidade.com",
    "site": "https://unidade.com"
  }
  ```
- **GET /gestor/unidades/{id}/**: Obter detalhes de uma unidade específica.
- **PUT /gestor/unidades/{id}/**: Atualizar uma unidade específica. Envie todos os campos obrigatórios.
- **PATCH /gestor/unidades/{id}/**: Atualizar parcialmente uma unidade específica. Envie apenas os campos que deseja alterar.
- **DELETE /gestor/unidades/{id}/**: Excluir uma unidade específica.

- **GET /gestor/livros/isbn-lookup/?isbn={isbn}**: Consulta metadados por ISBN na Open Library, traduz campos textuais para pt-BR (Google como primário, MyMemory como fallback) e retorna payload pronto para pré-preenchimento no frontend.

Exemplo de resposta:

```json
{
  "data": {
    "isbn": "9780140328721",
    "titulo": "Fantástico Sr. Raposo",
    "autor": "Roald Dahl",
    "editora": "Puffin",
    "data_publicacao": "1988-01-01",
    "paginas": 96,
    "capa": "https://covers.openlibrary.org/b/id/12345-L.jpg",
    "idioma": "Inglês",
    "source": "openlibrary"
  },
  "meta": {
    "source": "openlibrary",
    "translation_provider": "google",
    "translated_fields": ["titulo", "idioma"],
    "warnings": [],
    "cache_hit": false
  }
}
```

Status comuns:

- `400`: ISBN inválido ou ausente.
- `404`: ISBN não encontrado na Open Library.
- `503`: Falha de integração externa.

## Variáveis de Ambiente do Projeto

As variáveis abaixo estão documentadas também em `.env.example`:

- `DATABASE_URL`
- `SECRET_KEY`
- `DEBUG`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `CORS_ALLOWED_ORIGINS`

- `OPENLIBRARY_BASE_URL`
- `OPENLIBRARY_TIMEOUT_SECONDS`
- `OPENLIBRARY_USER_AGENT`
- `OPENLIBRARY_CONTACT_EMAIL`
- `ISBN_LOOKUP_CACHE_TTL_SECONDS`
- `GOOGLE_TRANSLATE_ENABLED`
- `GOOGLE_TRANSLATE_API_KEY`
- `MYMEMORY_BASE_URL`
- `MYMEMORY_CONTACT_EMAIL`
- `TRANSLATION_SOURCE_LANG`
- `TRANSLATION_TARGET_LANG`
- `TRANSLATION_FIELDS` (padrão: `titulo,idioma`; mantém nomes próprios como autor/editora sem tradução)

## Passo a Passo para Configurar o Banco de Dados

### 1. Criar as Migrações

Após configurar o projeto, crie as migrações para refletir as alterações no banco de dados:

```bash
python manage.py makemigrations gestor
```

### 2. Aplicar as Migrações

Aplique as migrações para criar as tabelas no banco de dados e popular a tabela de gêneros com valores iniciais:

```bash
python manage.py migrate
```

### 3. Verificar os Gêneros Criados

Os gêneros iniciais criados automaticamente são:

- Ficção
- Não Ficção
- Romance
- Fantasia
- Terror
- Biografia
- História
- Ciência

Você pode verificar os IDs dos gêneros no Django Admin ou via shell:

```bash
python manage.py shell
```

No shell, execute:

```python
from gestor.domain.entities.genero import Genero
for genero in Genero.objects.all():
    print(f"ID: {genero.id}, Nome: {genero.nome}")
```

Isso exibirá os IDs e nomes dos gêneros disponíveis.

## Problemas Comuns e Soluções

### Erro: "ModuleNotFoundError: No module named 'django'"

- Certifique-se de que o ambiente virtual está ativado.
- Instale as dependências com:
  ```bash
  pip install -r requirements.txt
  ```

## Contribuições

Contribuições são bem-vindas! Para contribuir com o projeto, siga os seguintes passos:

1.  Fork o repositório.
2.  Crie uma branch para a sua feature (git checkout -b feature/xyz).
3.  Faça o commit das suas alterações (git commit -am 'Adiciona nova feature').
4.  Push para a sua branch (git push origin feature/xyz).
5.  Abra um pull request.

## Licença

Este projeto está licenciado sob a MIT License.
