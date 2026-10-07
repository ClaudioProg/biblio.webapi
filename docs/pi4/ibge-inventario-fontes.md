# PI4 — Inventário de fontes IBGE para Acervo e Território

Atualização: 07/10/2026  
Município de referência: Santos/SP — código IBGE 3548500.

## 1. Decisão de recorte territorial

Para a primeira versão do painel, usar **bairro** como recorte principal sempre que a
variável oficial estiver disponível nesse nível. O bairro é mais compreensível para a
biblioteca e está alinhado ao Plano de Ação, que prevê leitura territorial por bairro/zona.

Setores censitários permanecem como fonte de maior detalhe para etapas futuras ou quando
a modelagem geoespacial exigir essa granularidade. Não misturar automaticamente bairros,
setores e áreas de ponderação: são unidades territoriais diferentes.

## 2. Fontes oficiais selecionadas

### 2.1 Base territorial e totais básicos — bairro

Fonte oficial:
https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/Agregados_por_Bairro_csv/Agregados_por_bairros_basico_BR_20260520.zip

Uso previsto:
- identificação do bairro;
- códigos territoriais;
- população e totais estruturais disponibilizados pelo arquivo básico;
- chave territorial para junção com os demais agregados de bairro.

Atualização oficial do arquivo: 20/05/2026.

### 2.2 Demografia — bairro

Fonte oficial:
https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/Agregados_por_Bairro_csv/Agregados_por_bairros_demografia_BR.zip

Uso previsto:
- estrutura etária;
- sexo;
- composição demográfica agregada.

Este conjunto será a fonte para as faixas etárias do dashboard.

### 2.3 Alfabetização — bairro

Fonte oficial:
https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/Agregados_por_Bairro_csv/Agregados_por_bairros_alfabetizacao_BR.zip

Uso previsto:
- condição de alfabetização por sexo e idade, conforme o dicionário oficial.

**Decisão metodológica:** não chamar alfabetização de “escolaridade”. Escolaridade/nível
de instrução pertence aos resultados da Amostra do Censo 2022 e tem outra granularidade
territorial. O painel deve identificar a dimensão corretamente como alfabetização, salvo se
for incorporada posteriormente uma fonte específica de educação em nível territorial
compatível.

### 2.4 Rendimento do responsável pelo domicílio — bairro

Fonte oficial:
https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/Agregados_por_bairros_renda_responsavel_BR_20260508_csv.zip

Dicionário oficial:
https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/dicionario_de_dados_renda_responsavel_20260508.xlsx

Uso previsto:
- caracterização agregada do rendimento dos responsáveis pelos domicílios.

Atualização oficial: 08/05/2026.

**Limitação obrigatória:** esse rendimento refere-se ao responsável pelo domicílio, não à
renda de todos os moradores. Não usar a variável para estimar pobreza, desigualdade geral
ou para ranquear bairros como se representasse a renda integral da população.

### 2.5 Dicionário geral dos agregados

Fonte oficial:
https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/dicionario_de_dados_agregados_por_setores_censitarios_20260520.xlsx

Regra: nenhum código Vxxxxx será usado no ETL ou no Power BI sem conferência prévia
neste dicionário.

### 2.6 Malha geográfica

Produto oficial:
Censo Demográfico 2022 — Malha de Setores Censitários / Arquivo geoespacial de Bairros.

Uso previsto:
- mapa de Santos;
- ligação espacial das métricas do IBGE ao bairro;
- futura análise de área de abrangência da Biblioteca Municipal Mário Faria.

Preferir GPKG/SHP oficial. Não desenhar polígonos manualmente.

## 3. Educação: decisão metodológica

O Plano de Ação menciona “escolaridade”. Os agregados do universo em bairro oferecem
**alfabetização**, que não é sinônimo de escolaridade ou nível de instrução.

Resultados mais completos de educação são provenientes do Questionário da Amostra.
Para a Amostra, a Área de Ponderação é o menor recorte geográfico oficial de divulgação
detalhada. Portanto:

1. primeira versão territorial por bairro: usar alfabetização, devidamente rotulada;
2. se o grupo considerar indispensável “nível de instrução”, criar uma segunda camada em
   Área de Ponderação ou município, sem fingir equivalência com bairros;
3. documentar essa diferença no relatório e no Power BI.

## 4. Regras de tratamento

- filtrar apenas Santos/SP (código municipal 3548500);
- manter os códigos territoriais como texto para não perder zeros;
- preservar o valor original e criar nomes analíticos em camada separada;
- valores de sigilo/supressão do IBGE (por exemplo, “x”) devem virar nulos, nunca zero;
- registrar, para cada variável: arquivo, código original, descrição oficial, unidade,
  transformação e indicador derivado;
- percentuais devem informar claramente o denominador;
- não somar médias;
- não preencher valores suprimidos por inferência;
- não armazenar dados pessoais de leitores na camada territorial.

## 5. Relação com dados da plataforma

A camada analítica da plataforma já fornece, de forma agregada:
- títulos;
- exemplares;
- unidades;
- usuários ativos;
- empréstimos totais, abertos e devolvidos;
- acervo por gênero, tipo de obra e unidade;
- circulação por unidade.

O cruzamento IBGE × acervo será descritivo. Dados sociodemográficos caracterizam o
território; não constituem prova de preferência literária nem permitem inferir automaticamente
“demanda” por gênero ou título.

## 6. Ordem de implementação

1. baixar e registrar as quatro bases oficiais;
2. conferir o dicionário e selecionar apenas variáveis necessárias;
3. filtrar Santos;
4. produzir uma tabela analítica única por bairro;
5. validar totais contra publicações oficiais;
6. incorporar a tabela tratada ao modelo do Power BI;
7. integrar a visualização na rota Dashboard;
8. validar com a Biblioteca Mário Faria;
9. documentar testes, limitações e feedback no relatório final.
