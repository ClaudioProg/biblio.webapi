let
    ApiBase = "https://biblio-webapi.onrender.com",
    Fonte = Json.Document(
        Web.Contents(
            ApiBase,
            [
                RelativePath = "gestor/analytics/powerbi/",
                Headers = [Accept = "application/json"],
                Timeout = #duration(0, 0, 2, 0)
            ]
        )
    )
in
    Fonte
