import html
import json
from typing import Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings


class TranslationService:
    def __init__(self):
        self.google_enabled = settings.GOOGLE_TRANSLATE_ENABLED
        self.google_api_key = settings.GOOGLE_TRANSLATE_API_KEY
        self.mymemory_base_url = settings.MYMEMORY_BASE_URL.rstrip("/")
        self.mymemory_contact_email = settings.MYMEMORY_CONTACT_EMAIL
        self.target_lang = self._normalize_lang(settings.TRANSLATION_TARGET_LANG)
        self.source_lang = self._normalize_source_lang(settings.TRANSLATION_SOURCE_LANG)
        allowed_fields = getattr(settings, "TRANSLATION_FIELDS", ["titulo", "idioma"])
        self.translation_fields = {str(field).strip() for field in allowed_fields if str(field).strip()}

    def translate_book_payload(self, payload: Dict) -> Tuple[Dict, Dict]:
        if not isinstance(payload, dict):
            return payload, {"provider": "none", "translated_fields": [], "warnings": []}

        translated = dict(payload)
        translated_fields = []
        warnings = []
        provider_used = "none"

        for field_name in ("titulo", "autor", "editora", "idioma"):
            if field_name not in self.translation_fields:
                continue
            value = str(translated.get(field_name) or "").strip()
            if not value:
                continue

            translated_value, provider, warning = self.translate_text(value)
            if warning:
                warnings.append(warning)
            if translated_value and translated_value != value:
                translated[field_name] = translated_value
                translated_fields.append(field_name)
                if provider_used == "none":
                    provider_used = provider

        return translated, {
            "provider": provider_used,
            "translated_fields": translated_fields,
            "warnings": warnings,
        }

    def translate_text(self, text: str) -> Tuple[str, str, Optional[str]]:
        if not text:
            return text, "none", None

        if self.google_enabled and self.google_api_key:
            translated = self._translate_google(text)
            if translated:
                return translated, "google", None

        translated = self._translate_mymemory(text)
        if translated:
            return translated, "mymemory", None

        return text, "none", "Falha ao traduzir texto por todos os provedores."

    def _translate_google(self, text: str) -> str:
        endpoint = f"https://translation.googleapis.com/language/translate/v2?key={self.google_api_key}"
        body = {
            "q": text,
            "target": self.target_lang,
            "format": "text",
        }
        if self.source_lang != "auto":
            body["source"] = self.source_lang

        request = Request(
            url=endpoint,
            method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )

        try:
            with urlopen(request, timeout=8) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw) if raw else {}
                translations = data.get("data", {}).get("translations", [])
                if translations:
                    return html.unescape(translations[0].get("translatedText", "")).strip()
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return ""
        return ""

    def _translate_mymemory(self, text: str) -> str:
        source = self.source_lang if self.source_lang != "auto" else "en"
        query = {
            "q": text,
            "langpair": f"{source}|{self.target_lang}",
        }
        if self.mymemory_contact_email:
            query["de"] = self.mymemory_contact_email

        url = f"{self.mymemory_base_url}/get?{urlencode(query)}"
        request = Request(url=url, method="GET", headers={"Accept": "application/json"})

        try:
            with urlopen(request, timeout=8) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw) if raw else {}
                translated = data.get("responseData", {}).get("translatedText", "")
                return html.unescape(str(translated)).strip()
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return ""

    def _normalize_lang(self, lang: str) -> str:
        value = (lang or "pt-BR").lower()
        if value.startswith("pt"):
            return "pt"
        return value.split("-")[0]

    def _normalize_source_lang(self, lang: str) -> str:
        value = (lang or "auto").lower()
        if value == "auto":
            return "auto"
        return value.split("-")[0]
