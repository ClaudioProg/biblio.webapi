let
    Registros = FontePowerBI[fato_devolucoes_mensal],
    Tabela = Table.FromRecords(Registros, {"mes", "unidade_id", "ibge_bairro_codigo", "genero", "tipo_obra", "devolucoes"}, MissingField.UseNull),
    Tipos = Table.TransformColumnTypes(
        Tabela,
        {
            {"mes", type date},
            {"unidade_id", Int64.Type},
            {"ibge_bairro_codigo", type text},
            {"genero", type text},
            {"tipo_obra", type text},
            {"devolucoes", Int64.Type}
        },
        "pt-BR"
    )
in
    Tipos
