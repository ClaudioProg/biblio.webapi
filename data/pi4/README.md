# Dados analíticos do PI4

Este diretório recebe os artefatos produzidos por scripts/pi4/build_ibge_santos.py.

Arquivos esperados:

- ibge_santos_bairros.csv: tabela analítica por bairro, pronta para importação no Power BI;
- ibge_santos_validation.json: relatório de validação, ausências e diferenças entre universos/fontes;
- ibge_santos_bairros.geojson: malha oficial dos 70 bairros de Santos, filtrada do shapefile do IBGE e validada contra os códigos da tabela analítica.

## Regras

- fonte exclusiva: arquivos públicos oficiais do Censo Demográfico 2022/IBGE;
- município: Santos/SP, código 3548500;
- granularidade principal: bairro;
- células ".", "x", "X" ou vazias são tratadas como ausentes, nunca como zero;
- um indicador derivado composto vira nulo se algum componente necessário estiver ausente;
- rendimento ausente em um bairro permanece nulo;
- os indicadores de rendimento referem-se à pessoa responsável pelo domicílio, conforme a definição do IBGE;
- a taxa de alfabetização usa somente as variáveis do próprio tema Alfabetização;
- nenhum dado pessoal de leitor é incorporado.

O snapshot deve ser regenerado sempre que a fonte oficial versionada no manifesto mudar.


## Malha geográfica

A malha é gerada por `scripts/pi4/build_ibge_santos_geojson.py` a partir do
arquivo oficial `SP_bairros_CD2022.zip`.

- sistema de referência da fonte: SIRGAS 2000 (EPSG:4674);
- somente registros com `CD_MUN = 3548500` são mantidos;
- os 70 códigos de bairro devem coincidir exatamente com
  `ibge_santos_bairros.csv`;
- nomes e códigos vêm do próprio IBGE, sem desenho manual de polígonos;
- o GeoJSON não contém dados pessoais.
