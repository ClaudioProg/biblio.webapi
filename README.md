# Bibliotecas Conectadas — API

Backend do Projeto Integrador IV — Ciências da Computação (UNIVESP), responsável pela gestão bibliográfica, autenticação, circulação, integração por ISBN e camada analítica utilizada pelo Dashboard e pelo Power BI.

A aplicação usa Django 5, Django REST Framework e PostgreSQL em produção.

## Arquitetura atual

- **Backend:** Django 5 + Django REST Framework.
- **Banco de dados em produção:** PostgreSQL/Neon.
- **Hospedagem da API:** Render.
- **Frontend:** Vercel.
- **Power BI:** Power BI Service, consumindo endpoint analítico autenticado.
- **Desenvolvimento local:** SQLite como fallback quando `DATABASE_URL` não está definida.

## Funcionalidades principais

- autenticação por token;
- gestão de unidades/bibliotecas;
- gestão de livros e exemplares;
- gestão de usuários/leitores;
- empréstimos e devoluções;
- gestão de contas de acesso administrativas;
- consulta assistida por ISBN;
- indicadores operacionais agregados;
- camada territorial com dados do IBGE;
- dataset específico para Power BI sem identificadores pessoais de leitores.

## Requisitos

- Python 3.10 ou superior;
- PostgreSQL recomendado para ambiente persistente;
- SQLite disponível como fallback local.

## Execução local

### 1. Clonar o repositório

```bash
git clone https://github.com/ClaudioProg/biblio.webapi.git
cd biblio.webapi
```

### 2. Criar ambiente virtual e instalar dependências

Windows:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurar ambiente

Exemplo mínimo para desenvolvimento:

```env
DATABASE_URL=
SECRET_KEY=chave-local
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:5173
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

Se `DATABASE_URL` estiver vazia, a aplicação usa SQLite local.

### 4. Aplicar migrações

```bash
python manage.py migrate
```

### 5. Executar

```bash
python manage.py runserver
```

Também pode ser usado:

```bash
python run.py dev
```

## Variáveis de ambiente relevantes

### Banco e segurança

- `DATABASE_URL`
- `DATABASE_SSL_REQUIRE`
- `SECRET_KEY`
- `DEBUG`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `CORS_ALLOWED_ORIGINS`

### ISBN e tradução

- `OPENLIBRARY_BASE_URL`
- `OPENLIBRARY_TIMEOUT_SECONDS`
- `OPENLIBRARY_USER_AGENT`
- `OPENLIBRARY_CONTACT_EMAIL`
- `BRASILAPI_BASE_URL`
- `BRASILAPI_TIMEOUT_SECONDS`
- `GOOGLE_BOOKS_BASE_URL`
- `GOOGLE_BOOKS_TIMEOUT_SECONDS`
- `GOOGLE_BOOKS_API_KEY`
- `ISBN_LOOKUP_CACHE_TTL_SECONDS`
- `GOOGLE_TRANSLATE_ENABLED`
- `GOOGLE_TRANSLATE_API_KEY`
- `MYMEMORY_BASE_URL`
- `MYMEMORY_CONTACT_EMAIL`
- `TRANSLATION_SOURCE_LANG`
- `TRANSLATION_TARGET_LANG`
- `TRANSLATION_FIELDS`

### Conta técnica do Power BI

- `BIBLIO_POWERBI_USERNAME`
- `BIBLIO_POWERBI_PASSWORD`
- `BIBLIO_POWERBI_EMAIL`

Essas variáveis criam/atualizam a conta técnica pertencente ao grupo `powerbi_reader`.

A senha nunca deve ser versionada. A autenticação Básica é aceita somente no endpoint analítico destinado ao Power BI; as rotas operacionais continuam protegidas pela autenticação por token do DRF.

## Endpoints principais

### Autenticação

- `POST /gestor/auth/login/`
- `POST /gestor/auth/logout/`
- `GET /gestor/auth/me/`
- `POST /gestor/auth/change-password/`

### Gestão

- `/gestor/livros/`
- `/gestor/unidades/`
- `/gestor/livro-unidades/`
- `/gestor/usuarios/`
- `/gestor/emprestimos/`
- `/gestor/acessos/`

Os endpoints registrados pelo DRF oferecem as operações compatíveis com cada recurso.

### ISBN

- `GET /gestor/livros/isbn-lookup/?isbn={isbn}`

O serviço consulta provedores configurados e devolve metadados normalizados para pré-preenchimento do formulário.

### Analytics

- `GET /gestor/analytics/resumo/`
  - indicadores operacionais agregados usados pelo Dashboard.

- `GET /gestor/analytics/territorio/`
  - indicadores territoriais do IBGE para Santos/SP.

- `GET /gestor/analytics/powerbi/`
  - dataset agregado destinado ao Power BI;
  - suporta autenticação Básica da conta técnica `powerbi_reader`;
  - não contém nome, e-mail, documento ou outro identificador pessoal de leitores.

## Power BI

O pacote versionado em `powerbi/` contém:

- projeto PBIP;
- modelo semântico;
- definição das cinco páginas do relatório;
- consultas Power Query;
- medidas DAX;
- documentação da fonte e da publicação.

O relatório foi publicado no Power BI Service e é incorporado ao frontend pela modalidade segura **Site ou portal**.

Não utilizar **Publicar na Web** para esse relatório.

Detalhes completos:

`powerbi/README.md`

## IBGE — Censo Demográfico 2022

A camada territorial está documentada em:

`docs/pi4/ibge-inventario-fontes.md`

O recorte confirmado atual usa 55 bairros de Santos/SP, preservando diferenças entre universos estatísticos e valores ausentes.

Os dados territoriais são usados para contextualização descritiva. Não devem ser convertidos automaticamente em inferências de preferência literária ou demanda de acervo.

## Estrutura resumida

```
biblio.webapi/
├── config/
├── data/
│   └── pi4/
├── docs/
│   └── pi4/
├── powerbi/
│   ├── pbip/
│   └── queries/
├── scripts/
│   └── pi4/
├── src/
│   └── gestor/
├── manage.py
├── requirements.txt
└── README.md
```

## Produção

- API: `https://biblio-webapi.onrender.com`
- Frontend: `https://bibliotecasconectadas.vercel.app`

## Segurança e privacidade

- rotas operacionais protegidas por autenticação;
- CORS restrito às origens previstas;
- credenciais e segredos apenas em variáveis de ambiente;
- dataset analítico do Power BI sem dados pessoais de leitores;
- dados territoriais provenientes de fontes públicas oficiais do IBGE.
