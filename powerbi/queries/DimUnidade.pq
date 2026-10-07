let
    Registros = FontePowerBI[dim_unidade],
    Tabela = Table.FromRecords(Registros),
    Tipos = Table.TransformColumnTypes(
        Tabela,
        {
            {"unidade_id", Int64.Type},
            {"unidade", type text},
            {"endereco", type text},
            {"ibge_bairro_codigo", type text},
            {"ibge_bairro_nome", type text},
            {"latitude", type number},
            {"longitude", type number}
        },
        "pt-BR"
    )
in
    Tipos
