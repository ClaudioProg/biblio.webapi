let
    Periodo = FontePowerBI[periodo],
    PrimeiroTexto = Periodo[primeiro_emprestimo],
    UltimoEmprestimoTexto = Periodo[ultimo_emprestimo],
    UltimaDevolucaoTexto = Periodo[ultima_devolucao],

    Hoje = Date.From(DateTime.LocalNow()),
    InicioBase =
        if PrimeiroTexto = null
        then Hoje
        else Date.FromText(PrimeiroTexto),

    Finais = List.RemoveNulls(
        {
            if UltimoEmprestimoTexto = null then null else Date.FromText(UltimoEmprestimoTexto),
            if UltimaDevolucaoTexto = null then null else Date.FromText(UltimaDevolucaoTexto)
        }
    ),
    FimBase = if List.Count(Finais) = 0 then Hoje else List.Max(Finais),

    Inicio = Date.StartOfYear(InicioBase),
    Fim = Date.EndOfYear(FimBase),
    Datas = List.Dates(
        Inicio,
        Duration.Days(Fim - Inicio) + 1,
        #duration(1, 0, 0, 0)
    ),
    Tabela = Table.FromList(Datas, Splitter.SplitByNothing(), {"Data"}),
    TipoData = Table.TransformColumnTypes(Tabela, {{"Data", type date}}),
    Ano = Table.AddColumn(TipoData, "Ano", each Date.Year([Data]), Int64.Type),
    MesNumero = Table.AddColumn(Ano, "MesNumero", each Date.Month([Data]), Int64.Type),
    Mes = Table.AddColumn(MesNumero, "Mes", each Date.MonthName([Data], "pt-BR"), type text),
    AnoMes = Table.AddColumn(Mes, "AnoMes", each Date.ToText([Data], "yyyy-MM"), type text),
    Trimestre = Table.AddColumn(
        AnoMes,
        "Trimestre",
        each "T" & Text.From(Date.QuarterOfYear([Data])),
        type text
    )
in
    Trimestre
