let
    Registros = FontePowerBI[fato_acervo],
    Tabela = Table.FromRecords(Registros, {"unidade_id", "ibge_bairro_codigo", "genero", "tipo_obra", "titulos", "exemplares", "emprestimos_abertos", "exemplares_disponiveis"}, MissingField.UseNull),
    Tipos = Table.TransformColumnTypes(
        Tabela,
        {
            {"unidade_id", Int64.Type},
            {"ibge_bairro_codigo", type text},
            {"genero", type text},
            {"tipo_obra", type text},
            {"titulos", Int64.Type},
            {"exemplares", Int64.Type},
            {"emprestimos_abertos", Int64.Type},
            {"exemplares_disponiveis", Int64.Type}
        },
        "pt-BR"
    )
in
    Tipos
