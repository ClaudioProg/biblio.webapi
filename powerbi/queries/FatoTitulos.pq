let
    Registros = FontePowerBI[fato_titulos],
    Tabela = Table.FromRecords(Registros),
    Tipos = Table.TransformColumnTypes(
        Tabela,
        {
            {"unidade_id", Int64.Type},
            {"ibge_bairro_codigo", type text},
            {"livro_id", Int64.Type},
            {"titulo", type text},
            {"autor", type text},
            {"isbn", type text},
            {"genero", type text},
            {"tipo_obra", type text},
            {"emprestimos_total", Int64.Type},
            {"emprestimos_abertos", Int64.Type},
            {"exemplares_atuais", Int64.Type},
            {"exemplares_disponiveis", Int64.Type}
        },
        "pt-BR"
    )
in
    Tipos
