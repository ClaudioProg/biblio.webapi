# Power BI — Bibliotecas Conectadas — PI4

Documentação do painel analítico do Projeto Integrador IV — Ciências da Computação (UNIVESP).

## Status atual — 08/10/2026

O painel está:

- modelado em projeto PBIP versionado no repositório;
- conectado ao endpoint analítico autenticado da API;
- composto por cinco páginas;
- validado no Power BI Desktop;
- publicado no Power BI Service;
- incorporado ao Dashboard da aplicação pela opção segura **Site ou portal**;
- utilizando o recorte territorial confirmado de 55 bairros de Santos/SP.

A incorporação segura pode exigir autenticação Microsoft/Power BI e depende de licença/capacidade compatível no tenant utilizado.

## 1. Fonte de dados

Endpoint:

`https://biblio-webapi.onrender.com/gestor/analytics/powerbi/`

O endpoint retorna somente dados agregados de:

- acervo;
- circulação;
- bibliotecas;
- território;
- qualidade das fontes do IBGE.

Não contém nome, e-mail, documento ou outro identificador pessoal de leitores.

## 2. Autenticação da fonte

No Power BI Desktop:

1. usar a URL base `https://biblio-webapi.onrender.com`;
2. selecionar autenticação **Básica**;
3. informar a conta técnica destinada ao Power BI.

A conta é mantida no backend por variáveis de ambiente:

- `BIBLIO_POWERBI_USERNAME`
- `BIBLIO_POWERBI_PASSWORD`
- `BIBLIO_POWERBI_EMAIL`

A senha não deve ser incluída em arquivos `.pq`, PBIP ou documentação versionada.

A autenticação Básica é aceita apenas no endpoint analítico do Power BI. As rotas operacionais da plataforma permanecem protegidas pela autenticação por token.

## 3. Modelo semântico

Tabelas principais:

- Bairros;
- Bibliotecas;
- Acervo;
- Circulação Mensal;
- Devoluções Mensais;
- Títulos;
- Calendário;
- Qualidade IBGE.

Relacionamentos são mantidos com filtro simples para evitar caminhos ambíguos.

A dimensão territorial se liga ao acervo e à circulação por meio da dimensão de biblioteca/unidade.

## 4. Tratamento de tabelas vazias

As tabelas fato preservam seu esquema mesmo quando a API retorna zero registros.

Isso é necessário, por exemplo, quando ainda não existem devoluções registradas: a tabela **Devoluções Mensais** pode permanecer vazia sem causar erro de atualização por ausência da coluna `mes`.

Não criar dados fictícios para preencher fatos vazios.

## 5. Páginas implementadas

### 5.1 Visão Geral

Exibe:

- títulos;
- exemplares;
- empréstimos abertos;
- exemplares disponíveis;
- exemplares por gênero;
- exemplares por tipo de obra;
- acervo e circulação por biblioteca.

### 5.2 Território

Exibe:

- 55 bairros no recorte confirmado;
- cobertura dos indicadores territoriais;
- mapa Azure Maps;
- tabela de indicadores sociodemográficos por bairro.

O mapa atualmente publicado usa **bolhas georreferenciadas por bairro**, dimensionadas pela população.

O arquivo GeoJSON oficial dos bairros permanece versionado em:

`data/pi4/ibge_santos_bairros.geojson`

e pode ser utilizado em refinamentos futuros para representação por polígonos. A camada poligonal não deve ser documentada como ativa enquanto não estiver efetivamente aplicada ao relatório publicado.

### 5.3 Acervo × Território

Possui filtro de biblioteca e apresenta, lado a lado:

- composição do acervo;
- população do bairro da unidade;
- taxa de alfabetização;
- rendimento mediano da pessoa responsável pelo domicílio.

As medidas territoriais exigem a seleção de uma única biblioteca. Quando nenhuma unidade específica está selecionada, esses indicadores permanecem em branco por decisão metodológica.

### 5.4 Circulação

Exibe:

- empréstimos iniciados;
- devoluções;
- títulos com circulação;
- exemplares disponíveis;
- série mensal de circulação;
- títulos com circulação.

Quando não há devoluções registradas, o indicador permanece vazio; não é convertido artificialmente em zero.

### 5.5 Qualidade e Metodologia

Exibe:

- bairros no recorte;
- bairros com e sem rendimento publicado;
- diferenças entre os universos Básico e Demografia;
- diferenças entre total demográfico e soma das faixas etárias;
- tabela de cobertura territorial.

Essas diferenças são preservadas e documentadas, não corrigidas artificialmente.

## 6. Regras metodológicas

Os indicadores territoriais têm finalidade descritiva.

Não inferir automaticamente:

- preferência literária do bairro;
- demanda por gênero;
- déficit de acervo;
- causalidade entre perfil sociodemográfico e circulação.

Rendimento refere-se à **pessoa responsável pelo domicílio**, e não à renda integral de todos os moradores.

Alfabetização não deve ser apresentada como sinônimo de escolaridade ou nível de instrução.

## 7. Publicação no Power BI Service

Publicação realizada a partir do Power BI Desktop no workspace disponível da conta institucional.

Fluxo adotado:

1. carregar e validar os dados no Power BI Desktop;
2. publicar o relatório no Power BI Service;
3. abrir o relatório no Service;
4. usar **Arquivo → Inserir relatório → Site ou portal**;
5. copiar a URL segura de incorporação;
6. integrar a URL ao frontend.

Não usar **Publicar na Web**, pois essa modalidade cria acesso público ao conteúdo.

## 8. Incorporação no frontend

O Dashboard da aplicação incorpora o relatório em um `iframe`.

O frontend aceita:

`VITE_POWERBI_EMBED_URL`

como override opcional da URL incorporada.

Na ausência dessa variável, o componente utiliza a URL segura atualmente publicada para o PI4.

A alteração futura do relatório ou da URL de incorporação pode ser feita por variável de ambiente sem necessidade de alterar a lógica do Dashboard.

## 9. Atualização dos dados

O endpoint analítico é dinâmico para acervo e circulação.

As bases territoriais do IBGE são versionadas no repositório e só devem ser substituídas quando houver nova versão oficial documentada.

### Power BI Desktop

Atualização manual validada com autenticação Básica.

### Power BI Service

Após a publicação, a atualização automática do modelo semântico deve usar credenciais da fonte Web em modo **Básico**.

A configuração e o teste de atualização agendada no Service devem ser verificados separadamente da publicação e da incorporação do relatório.

## 10. Licenciamento

A incorporação segura **Site ou portal** respeita as permissões do Power BI.

Seu funcionamento contínuo depende de:

- autenticação Microsoft adequada;
- licença Power BI compatível ou capacidade aplicável;
- políticas do tenant Microsoft.

A publicação técnica do relatório não deve ser tratada como garantia de acesso irrestrito para qualquer usuário externo.

## 11. Evidências já obtidas

Concluído em 08/10/2026:

- conexão da fonte autenticada;
- carregamento do modelo no Power BI Desktop;
- tratamento de fatos vazios;
- validação das cinco páginas;
- teste do mapa;
- publicação no Power BI Service;
- geração de link seguro de incorporação;
- integração do Power BI no frontend;
- build e testes automatizados do frontend após a integração.

Ainda devem ser registrados conforme o fechamento acadêmico:

- teste de atualização automática no Power BI Service;
- feedback da Biblioteca Municipal Mário Faria;
- capturas finais das páginas e da incorporação para o relatório do PI4.
