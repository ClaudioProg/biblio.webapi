# Power BI — Bibliotecas Conectadas — PI4

Este diretório contém o pacote de modelagem para o painel analítico do Projeto
Integrador IV.

A fonte é o endpoint autenticado:

`https://biblio-webapi.onrender.com/gestor/analytics/powerbi/`

O endpoint retorna somente dados agregados e metadados de acervo, circulação e
território. Não inclui nome, e-mail, documento ou qualquer outro identificador
de leitores.

## 1. Conexão

No Power BI Desktop:

1. Obter dados > Web.
2. Usar a URL base `https://biblio-webapi.onrender.com`.
3. Escolher autenticação **Básica**.
4. Informar uma conta Django destinada ao Power BI.
5. Criar a consulta `FontePowerBI` com o conteúdo de
   `queries/FontePowerBI.pq`.
6. Criar as demais consultas como referências à `FontePowerBI`.

Não colocar usuário ou senha dentro dos arquivos `.pq`.

A autenticação Básica foi habilitada apenas nesse endpoint analítico. As rotas
operacionais da plataforma continuam usando TokenAuthentication.

## 2. Consultas

Criar com estes nomes:

- FontePowerBI
- DimBairro
- DimUnidade
- FatoAcervo
- FatoCirculacaoMensal
- FatoDevolucoesMensal
- FatoTitulos
- DimCalendario
- QualidadeIBGE

## 3. Relacionamentos

Usar relações de filtro simples:

- `DimBairro[cd_bairro]` 1 → * `DimUnidade[ibge_bairro_codigo]`
- `DimUnidade[unidade_id]` 1 → * `FatoAcervo[unidade_id]`
- `DimUnidade[unidade_id]` 1 → * `FatoCirculacaoMensal[unidade_id]`
- `DimUnidade[unidade_id]` 1 → * `FatoDevolucoesMensal[unidade_id]`
- `DimUnidade[unidade_id]` 1 → * `FatoTitulos[unidade_id]`
- `DimCalendario[MesInicio]` 1 → * `FatoCirculacaoMensal[mes]`
- `DimCalendario[MesInicio]` 1 → * `FatoDevolucoesMensal[mes]`

Não criar relações adicionais das tabelas fato diretamente com `DimBairro`.
O bairro chega aos fatos pela dimensão de unidade; isso evita caminhos
ambíguos.

## 4. Medidas

Criar as medidas de `medidas.dax`.

As medidas territoriais associadas à biblioteca usam `TREATAS` e exigem uma
única unidade selecionada. Isso evita transformar a localização de uma
biblioteca em uma inferência sobre toda a população de Santos.

Não criar nesta etapa:
- “índice de déficit do acervo”;
- “preferência literária do bairro”;
- “demanda estimada por gênero”.

Esses indicadores exigiriam uma regra metodológica validada com a biblioteca
parceira e não podem ser deduzidos apenas das variáveis sociodemográficas.

## 5. Páginas recomendadas

### Página 1 — Visão Geral

Cards:
- Títulos
- Exemplares
- Exemplares disponíveis
- Empréstimos abertos
- Empréstimos iniciados
- Devoluções

Visuais:
- exemplares por gênero;
- exemplares por tipo de obra;
- acervo e circulação por unidade.

### Página 2 — Território

Usar o visual **Azure Maps**.

Camada de referência:
`data/pi4/ibge_santos_bairros.geojson`

Campo de localização:
`DimBairro[cd_bairro]`

A propriedade de ligação do GeoJSON é:
`cd_bairro`

O arquivo contém os 70 bairros oficiais de Santos. Utilizar formatação
condicional separadamente para:
- população;
- participação das faixas etárias;
- taxa de alfabetização de 15 anos ou mais;
- rendimento mediano da pessoa responsável pelo domicílio.

Valores ausentes devem permanecer sem preenchimento analítico, nunca ser
convertidos em zero.

### Página 3 — Acervo × Território

Slicer de uma única biblioteca.

Exibir lado a lado:
- composição do acervo por gênero e tipo;
- população do bairro da unidade;
- distribuição etária do bairro;
- taxa de alfabetização;
- rendimento mediano do responsável.

Título sugerido:
“Contexto territorial da unidade e composição do acervo”.

Não usar linguagem causal (“a população prefere”, “há demanda por”) sem
evidência específica.

### Página 4 — Circulação

- série mensal de empréstimos;
- série mensal de devoluções;
- ranking de títulos;
- filtros por unidade, gênero e tipo de obra;
- disponibilidade atual.

### Página 5 — Qualidade e Metodologia

Exibir:
- 70 bairros no recorte;
- 55 bairros com rendimento publicado;
- 15 bairros sem rendimento publicado;
- diferenças entre os universos Básico/Demografia;
- diferenças entre total demográfico e soma das faixas;
- fonte: IBGE — Censo Demográfico 2022;
- indicação de que rendimento é da pessoa responsável pelo domicílio.

## 6. Mapa

O GeoJSON foi gerado a partir de
`SP_bairros_CD2022.zip`, malha oficial do IBGE, em SIRGAS 2000 (EPSG:4674),
e validado contra os 70 códigos da tabela analítica.

No Azure Maps, a camada de referência pode ser vinculada aos dados pelo campo
`cd_bairro`, presente tanto na dimensão quanto nas propriedades do GeoJSON.

## 7. Publicação e incorporação

Para a versão final, preferir **incorporação segura** do Power BI Service:

1. publicar o relatório no Power BI Service;
2. conceder acesso apenas aos usuários autorizados;
3. Arquivo > Inserir relatório > Site ou portal;
4. copiar a URL segura de incorporação;
5. configurar essa URL como `VITE_POWERBI_EMBED_URL` no projeto Vercel;
6. republicar o frontend.

Não usar “Publicar na Web” como atalho para conteúdo que não tenha sido
explicitamente autorizado para acesso público.

A incorporação segura exige autenticação no Power BI e licenciamento/capacidade
compatível com a conta Microsoft da instituição.

## 8. Atualização

Ao publicar o modelo semântico no Power BI Service, configurar as credenciais
da fonte Web como **Básica**. Não usar o modo Web API para o refresh no
serviço.

O endpoint analítico é dinâmico para acervo e circulação. As bases IBGE estão
versionadas no repositório e só devem ser substituídas quando houver uma nova
versão oficial documentada.

## 9. Evidências para o relatório final

Registrar:
- data da atualização do conjunto de dados;
- número de linhas por tabela;
- captura das relações do modelo;
- páginas do painel;
- teste de filtros;
- teste do mapa;
- teste de refresh;
- teste de incorporação na plataforma;
- feedback da Biblioteca Municipal Mário Faria.
