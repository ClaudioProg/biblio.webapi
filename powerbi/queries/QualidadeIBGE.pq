let
    Registro = FontePowerBI[qualidade_ibge],
    Tabela = Table.FromRecords({Registro}),
    Tipos = Table.TransformColumnTypes(
        Tabela,
        {
            {"bairros_total", Int64.Type},
            {"bairros_com_renda", Int64.Type},
            {"bairros_sem_renda", Int64.Type},
            {"diferencas_total_basico_demografia", Int64.Type},
            {"diferencas_total_demografia_faixas_etarias", Int64.Type}
        }
    )
in
    Tipos
