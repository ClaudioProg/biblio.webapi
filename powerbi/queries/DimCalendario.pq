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

    Inicio = Date.StartOfMonth(InicioBase),
    Fim = Date.StartOfMonth(FimBase),
    Meses = List.Generate(
        () => Inicio,
        each _ <= Fim,
        each Date.AddMonths(_, 1)
    ),
    Tabela = Table.FromList(Meses, Splitter.SplitByNothing(), {"MesInicio"}),
    TipoData = Table.TransformColumnTypes(Tabela, {{"MesInicio", type date}}),
    Ano = Table.AddColumn(TipoData, "Ano", each Date.Year([MesInicio]), Int64.Type),
    MesNumero = Table.AddColumn(Ano, "MesNumero", each Date.Month([MesInicio]), Int64.Type),
    Mes = Table.AddColumn(
        MesNumero,
        "Mes",
        each Date.MonthName([MesInicio], "pt-BR"),
        type text
    ),
    AnoMes = Table.AddColumn(
        Mes,
        "AnoMes",
        each Date.ToText([MesInicio], "yyyy-MM"),
        type text
    ),
    Trimestre = Table.AddColumn(
        AnoMes,
        "Trimestre",
        each "T" & Text.From(Date.QuarterOfYear([MesInicio])),
        type text
    )
in
    Trimestre
