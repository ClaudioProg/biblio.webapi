import json
import re
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from django.conf import settings


class ExternalServiceError(Exception):
    pass


class InvalidIsbnError(Exception):
    pass


class IsbnNotFoundError(Exception):
    pass


def normalize_isbn(raw_isbn: str) -> str:
    cleaned = re.sub(r"[^0-9Xx]", "", raw_isbn or "").upper()
    if len(cleaned) == 10 and _is_valid_isbn10(cleaned):
        return cleaned
    if len(cleaned) == 13 and _is_valid_isbn13(cleaned):
        return cleaned
    raise InvalidIsbnError("ISBN inválido. Use ISBN-10 ou ISBN-13 válido.")


def _is_valid_isbn10(isbn10: str) -> bool:
    if not re.fullmatch(r"\d{9}[\dX]", isbn10):
        return False
    total = 0
    for idx, char in enumerate(isbn10):
        value = 10 if char == "X" else int(char)
        total += value * (10 - idx)
    return total % 11 == 0


def _is_valid_isbn13(isbn13: str) -> bool:
    if not re.fullmatch(r"\d{13}", isbn13):
        return False
    total = 0
    for idx, char in enumerate(isbn13[:-1]):
        weight = 1 if idx % 2 == 0 else 3
        total += int(char) * weight
    check_digit = (10 - (total % 10)) % 10
    return check_digit == int(isbn13[-1])


class OpenLibraryLookupService:
    def __init__(self):
        self.base_url = settings.OPENLIBRARY_BASE_URL.rstrip("/")
        self.timeout = settings.OPENLIBRARY_TIMEOUT_SECONDS

    def lookup(self, isbn: str) -> dict:
        normalized_isbn = normalize_isbn(isbn)
        edition_data = self._fetch_edition_json(normalized_isbn)
        books_data = self._fetch_books_api(normalized_isbn)

        payload = self._map_to_payload(normalized_isbn, edition_data, books_data)
        if not payload.get("titulo") and not payload.get("autor"):
            raise IsbnNotFoundError("ISBN não encontrado na Open Library.")
        return payload

    def _fetch_edition_json(self, isbn: str) -> dict:
        url = f"{self.base_url}/isbn/{isbn}.json"
        try:
            return self._request_json(url)
        except ExternalServiceError:
            return {}

    def _fetch_books_api(self, isbn: str) -> dict:
        query = urlencode(
            {
                "bibkeys": f"ISBN:{isbn}",
                "jscmd": "data",
                "format": "json",
            }
        )
        url = f"{self.base_url}/api/books?{query}"
        try:
            data = self._request_json(url)
        except ExternalServiceError:
            return {}
        return data.get(f"ISBN:{isbn}", {}) if isinstance(data, dict) else {}

    def _request_json(self, url: str) -> dict:
        request = Request(url=url, method="GET", headers=self._build_headers())
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ExternalServiceError("Falha ao consultar Open Library.") from exc

    def _build_headers(self) -> dict:
        user_agent = settings.OPENLIBRARY_USER_AGENT
        contact_email = settings.OPENLIBRARY_CONTACT_EMAIL
        if contact_email:
            user_agent = f"{user_agent} ({contact_email})"
        headers = {
            "Accept": "application/json",
            "User-Agent": user_agent,
        }
        if contact_email:
            headers["From"] = contact_email
        return headers

    def _map_to_payload(self, isbn: str, edition_data: dict, books_data: dict) -> dict:
        titulo = books_data.get("title") or edition_data.get("title") or ""
        autor = self._extract_author(books_data, edition_data)
        editora = self._extract_publisher(books_data, edition_data)
        data_publicacao = self._normalize_date(
            books_data.get("publish_date") or edition_data.get("publish_date")
        )
        capa = self._extract_cover(books_data, edition_data)
        idioma = self._extract_language(books_data, edition_data)
        paginas = books_data.get("number_of_pages") or edition_data.get("number_of_pages")

        return {
            "isbn": isbn,
            "titulo": titulo,
            "autor": autor,
            "editora": editora,
            "data_publicacao": data_publicacao,
            "paginas": paginas,
            "capa": capa,
            "idioma": idioma,
            "source": "openlibrary",
        }

    def _extract_author(self, books_data: dict, edition_data: dict) -> str:
        authors = books_data.get("authors")
        if isinstance(authors, list) and authors:
            names = [a.get("name", "") for a in authors if isinstance(a, dict)]
            names = [n for n in names if n]
            if names:
                return ", ".join(names)

        by_statement = edition_data.get("by_statement")
        if isinstance(by_statement, str) and by_statement.strip():
            return by_statement.strip()

        return ""

    def _extract_publisher(self, books_data: dict, edition_data: dict) -> str:
        publishers = books_data.get("publishers")
        if isinstance(publishers, list) and publishers:
            first = publishers[0]
            if isinstance(first, dict):
                return first.get("name", "")
            if isinstance(first, str):
                return first

        publishers = edition_data.get("publishers")
        if isinstance(publishers, list) and publishers:
            first = publishers[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return first.get("name", "")

        return ""

    def _extract_cover(self, books_data: dict, edition_data: dict) -> str:
        cover_data = books_data.get("cover")
        if isinstance(cover_data, dict):
            return (
                cover_data.get("large")
                or cover_data.get("medium")
                or cover_data.get("small")
                or ""
            )

        covers = edition_data.get("covers")
        if isinstance(covers, list) and covers:
            return f"https://covers.openlibrary.org/b/id/{covers[0]}-L.jpg"

        return ""

    def _extract_language(self, books_data: dict, edition_data: dict) -> str:
        language_map = {
            "eng": "English",
            "por": "Portuguese",
            "spa": "Spanish",
            "fre": "French",
            "ger": "German",
            "ita": "Italian",
        }

        language_list = edition_data.get("languages")
        if isinstance(language_list, list) and language_list:
            first = language_list[0]
            if isinstance(first, dict):
                key = first.get("key", "")
                if key.startswith("/languages/"):
                    code = key.split("/")[-1]
                    return language_map.get(code, code)

        return books_data.get("languages", "") if isinstance(books_data.get("languages"), str) else ""

    def _normalize_date(self, publish_date):
        if not publish_date:
            return ""

        text = str(publish_date).strip()

        for date_format in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, date_format).strftime("%Y-%m-%d")
            except ValueError:
                continue

        year_match = re.search(r"\b(\d{4})\b", text)
        if year_match:
            return f"{year_match.group(1)}-01-01"

        return ""


def _isbn10_to_isbn13(isbn10: str) -> str | None:
    normalized = normalize_isbn(isbn10)
    if len(normalized) != 10:
        return None

    base = "978" + normalized[:9]
    total = sum(
        int(char) * (1 if index % 2 == 0 else 3)
        for index, char in enumerate(base)
    )
    check = (10 - (total % 10)) % 10
    return f"{base}{check}"


def _isbn13_to_isbn10(isbn13: str) -> str | None:
    normalized = normalize_isbn(isbn13)
    if len(normalized) != 13 or not normalized.startswith("978"):
        return None

    base = normalized[3:12]
    total = sum(int(char) * (10 - index) for index, char in enumerate(base))
    remainder = total % 11
    check_value = (11 - remainder) % 11
    check = "X" if check_value == 10 else str(check_value)
    candidate = f"{base}{check}"
    return candidate if _is_valid_isbn10(candidate) else None


def isbn_equivalents(isbn: str) -> set[str]:
    normalized = normalize_isbn(isbn)
    values = {normalized}

    if len(normalized) == 10:
        converted = _isbn10_to_isbn13(normalized)
        if converted:
            values.add(converted)
    elif len(normalized) == 13:
        converted = _isbn13_to_isbn10(normalized)
        if converted:
            values.add(converted)

    return values


class GoogleBooksLookupService:
    def __init__(self):
        self.base_url = settings.GOOGLE_BOOKS_BASE_URL.rstrip("/")
        self.timeout = settings.GOOGLE_BOOKS_TIMEOUT_SECONDS
        self.api_key = settings.GOOGLE_BOOKS_API_KEY

    def lookup(self, isbn: str) -> dict:
        normalized_isbn = normalize_isbn(isbn)
        params = {
            "q": f"isbn:{normalized_isbn}",
            "maxResults": 5,
            "printType": "books",
            "projection": "full",
        }
        if self.api_key:
            params["key"] = self.api_key

        url = f"{self.base_url}/volumes?{urlencode(params)}"
        data = self._request_json(url)
        item = self._find_exact_item(normalized_isbn, data)

        if not item:
            raise IsbnNotFoundError("ISBN não encontrado no Google Books.")

        payload = self._map_to_payload(normalized_isbn, item)
        if not payload.get("titulo") and not payload.get("autor"):
            raise IsbnNotFoundError("ISBN não encontrado no Google Books.")
        return payload

    def _request_json(self, url: str) -> dict:
        request = Request(
            url=url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": settings.OPENLIBRARY_USER_AGENT,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ExternalServiceError("Falha ao consultar Google Books.") from exc

    def _find_exact_item(self, isbn: str, data: dict) -> dict:
        expected = isbn_equivalents(isbn)
        items = data.get("items", []) if isinstance(data, dict) else []

        for item in items:
            if not isinstance(item, dict):
                continue
            volume = item.get("volumeInfo", {})
            identifiers = volume.get("industryIdentifiers", [])
            found = set()

            for identifier in identifiers:
                if not isinstance(identifier, dict):
                    continue
                raw = identifier.get("identifier")
                if not raw:
                    continue
                try:
                    found.add(normalize_isbn(str(raw)))
                except InvalidIsbnError:
                    continue

            if expected & found:
                return item

        return {}

    def _map_to_payload(self, isbn: str, item: dict) -> dict:
        volume = item.get("volumeInfo", {}) if isinstance(item, dict) else {}
        authors = volume.get("authors", [])
        author = ", ".join(
            str(name).strip()
            for name in authors
            if str(name).strip()
        ) if isinstance(authors, list) else ""

        image_links = volume.get("imageLinks", {})
        cover = ""
        if isinstance(image_links, dict):
            cover = (
                image_links.get("extraLarge")
                or image_links.get("large")
                or image_links.get("medium")
                or image_links.get("small")
                or image_links.get("thumbnail")
                or image_links.get("smallThumbnail")
                or ""
            )
            if cover.startswith("http://"):
                cover = "https://" + cover[len("http://"):]

        language_map = {
            "pt": "Portuguese",
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "it": "Italian",
        }
        language = str(volume.get("language") or "").strip()

        return {
            "isbn": isbn,
            "titulo": str(volume.get("title") or "").strip(),
            "autor": author,
            "editora": str(volume.get("publisher") or "").strip(),
            "data_publicacao": self._normalize_date(volume.get("publishedDate")),
            "paginas": volume.get("pageCount") or None,
            "capa": cover,
            "idioma": language_map.get(language, language),
            "source": "googlebooks",
        }

    def _normalize_date(self, publish_date):
        if not publish_date:
            return ""

        text = str(publish_date).strip()
        for date_format in ("%Y-%m-%d", "%Y-%m", "%Y/%m/%d"):
            try:
                parsed = datetime.strptime(text, date_format)
                if date_format == "%Y-%m":
                    return parsed.strftime("%Y-%m-01")
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue

        year_match = re.search(r"\b(\d{4})\b", text)
        if year_match:
            return f"{year_match.group(1)}-01-01"
        return ""


class BookMetadataLookupService:
    def __init__(self):
        self.providers = [
            OpenLibraryLookupService(),
            GoogleBooksLookupService(),
        ]

    def lookup(self, isbn: str) -> dict:
        normalized_isbn = normalize_isbn(isbn)
        external_errors = []

        for provider in self.providers:
            try:
                return provider.lookup(normalized_isbn)
            except IsbnNotFoundError:
                continue
            except ExternalServiceError as exc:
                external_errors.append(exc)

        if external_errors:
            raise ExternalServiceError(
                "Não foi possível concluir a consulta nas bases bibliográficas agora."
            )

        raise IsbnNotFoundError(
            "ISBN não encontrado nas bases bibliográficas consultadas."
        )
