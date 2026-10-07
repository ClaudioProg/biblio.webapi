let
    Registros = FontePowerBI[dim_bairro],
    Tabela = Table.FromRecords(Registros),
    Tipos = Table.TransformColumnTypes(
        Tabela,
        {
            {"cd_bairro", type text},
            {"bairro", type text},
            {"area_km2", type number},
            {"populacao_total", Int64.Type},
            {"populacao_demografia", Int64.Type},
            {"idade_0_14", Int64.Type},
            {"idade_15_29", Int64.Type},
            {"idade_30_59", Int64.Type},
            {"idade_60_mais", Int64.Type},
            {"populacao_idade_classificada", Int64.Type},
            {"populacao_15_mais_alfabetizacao", Int64.Type},
            {"alfabetizados_15_mais", Int64.Type},
            {"taxa_alfabetizacao_15_mais_pct", type number},
            {"responsaveis_dpp_ocupados", Int64.Type},
            {"renda_responsavel_media", type number},
            {"renda_responsavel_mediana", type number},
            {"renda_disponivel", type logical}
        },
        "pt-BR"
    )
in
    Tipos
