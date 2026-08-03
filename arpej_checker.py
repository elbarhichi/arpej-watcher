#!/usr/bin/env python3
"""Vérifie les disponibilités des résidences ARPEJ sélectionnées.

Le programme interroge l'API JSON publique utilisée par la page ARPEJ, conserve
un historique SQLite et signale les disponibilités.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.json")
USER_AGENT = "ARPEJAvailabilityChecker/1.0 (+hourly personal availability check)"


class CheckerError(RuntimeError):
    """Erreur contrôlée du checker."""


@dataclass(frozen=True)
class Config:
    api_url: str
    city_ids: tuple[str, ...]
    expected_residence_ids: frozenset[int]
    timeout_seconds: float
    retries: int
    active_start_hour: int
    active_end_hour: int
    data_directory: Path
    secrets_file: Path
    ntfy_topic_url_environment_variable: str
    webhook_url_environment_variable: str
    telegram_bot_token_environment_variable: str
    telegram_chat_id_environment_variable: str


@dataclass(frozen=True)
class Residence:
    residence_id: int
    title: str
    city: str
    url: str
    available_rooms: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_within_active_hours(
    config: Config, current_time: datetime | None = None
) -> bool:
    local_time = current_time or datetime.now().astimezone()
    return config.active_start_hour <= local_time.hour <= config.active_end_hour


def load_config(path: Path) -> Config:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CheckerError(f"Configuration introuvable : {path}") from exc
    except json.JSONDecodeError as exc:
        raise CheckerError(f"Configuration JSON invalide : {exc}") from exc

    api_url = str(raw.get("api_url", "")).strip()
    parsed_url = urlparse(api_url)
    if parsed_url.scheme != "https" or parsed_url.hostname not in {
        "arpej.fr",
        "www.arpej.fr",
    }:
        raise CheckerError("api_url doit être une URL HTTPS du domaine arpej.fr")

    city_ids = tuple(str(value).strip() for value in raw.get("city_ids", []))
    if not city_ids or any(not value.isdigit() for value in city_ids):
        raise CheckerError("city_ids doit contenir au moins un identifiant numérique")

    expected_ids = frozenset(int(value) for value in raw.get("expected_residence_ids", []))
    if not expected_ids:
        raise CheckerError("expected_residence_ids ne peut pas être vide")

    retries = int(raw.get("request_retries", 3))
    timeout = float(raw.get("request_timeout_seconds", 20))
    if retries < 1 or timeout <= 0:
        raise CheckerError("Le timeout et le nombre de tentatives doivent être positifs")

    active_hours = raw.get("active_hours", {})
    if not isinstance(active_hours, dict):
        raise CheckerError("active_hours doit être un objet JSON")
    active_start_hour = int(active_hours.get("start", 8))
    active_end_hour = int(active_hours.get("end", 18))
    if not 0 <= active_start_hour <= active_end_hour <= 23:
        raise CheckerError("La plage active doit respecter 0 <= start <= end <= 23")

    data_value = Path(str(raw.get("data_directory", "data")))
    data_directory = data_value if data_value.is_absolute() else path.parent / data_value
    secrets_value = Path(str(raw.get("secrets_file", "secrets.json")))
    secrets_file = (
        secrets_value if secrets_value.is_absolute() else path.parent / secrets_value
    )

    return Config(
        api_url=api_url,
        city_ids=city_ids,
        expected_residence_ids=expected_ids,
        timeout_seconds=timeout,
        retries=retries,
        active_start_hour=active_start_hour,
        active_end_hour=active_end_hour,
        data_directory=data_directory.resolve(),
        secrets_file=secrets_file.resolve(),
        ntfy_topic_url_environment_variable=str(
            raw.get(
                "ntfy_topic_url_environment_variable",
                "ARPEJ_NTFY_TOPIC_URL",
            )
        ),
        webhook_url_environment_variable=str(
            raw.get("webhook_url_environment_variable", "ARPEJ_WEBHOOK_URL")
        ),
        telegram_bot_token_environment_variable=str(
            raw.get(
                "telegram_bot_token_environment_variable",
                "ARPEJ_TELEGRAM_BOT_TOKEN",
            )
        ),
        telegram_chat_id_environment_variable=str(
            raw.get(
                "telegram_chat_id_environment_variable",
                "ARPEJ_TELEGRAM_CHAT_ID",
            )
        ),
    )


def build_api_url(config: Config) -> str:
    params: list[tuple[str, str]] = [
        ("lang", "fr"),
        ("display", "map"),
    ]
    params.extend(("related_city[]", city_id) for city_id in config.city_ids)
    params.extend(
        [
            ("price_from", "0"),
            ("price_to", "1000"),
            ("show_if_full", "true"),
            ("show_if_colocations", "false"),
        ]
    )
    separator = "&" if urlparse(config.api_url).query else "?"
    return f"{config.api_url}{separator}{urlencode(params)}"


def fetch_payload(config: Config) -> dict[str, Any]:
    request = Request(
        build_api_url(config),
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    last_error: Exception | None = None

    for attempt in range(1, config.retries + 1):
        try:
            with urlopen(request, timeout=config.timeout_seconds) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise CheckerError("La réponse ARPEJ n'est pas un objet JSON")
            return payload
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504}:
                break
        except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_error = exc

        if attempt < config.retries:
            time.sleep(2 ** (attempt - 1))

    raise CheckerError(
        f"Impossible d'interroger ARPEJ après {config.retries} tentative(s) : {last_error}"
    )


def parse_available_rooms(value: Any, residence_id: int) -> int:
    if value is None or isinstance(value, bool):
        raise CheckerError(
            f"available_rooms absent ou invalide pour la résidence {residence_id}"
        )
    try:
        rooms = int(value)
    except (TypeError, ValueError) as exc:
        raise CheckerError(
            f"available_rooms invalide pour la résidence {residence_id} : {value!r}"
        ) from exc
    if rooms < 0:
        raise CheckerError(f"Nombre de logements négatif pour la résidence {residence_id}")
    return rooms


def parse_residences(payload: dict[str, Any]) -> list[Residence]:
    raw_residences = payload.get("residences")
    if not isinstance(raw_residences, list):
        raise CheckerError("Le champ residences est absent de la réponse ARPEJ")

    residences: list[Residence] = []
    seen_ids: set[int] = set()
    for item in raw_residences:
        if not isinstance(item, dict) or not isinstance(item.get("extra_data"), dict):
            raise CheckerError("Structure de résidence ARPEJ inattendue")
        extra = item["extra_data"]
        try:
            residence_id = int(item["ID"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CheckerError("Identifiant de résidence absent ou invalide") from exc
        if residence_id in seen_ids:
            raise CheckerError(f"Résidence dupliquée dans la réponse : {residence_id}")
        seen_ids.add(residence_id)

        residences.append(
            Residence(
                residence_id=residence_id,
                title=str(item.get("title") or f"Résidence {residence_id}").strip(),
                city=str(extra.get("city") or "Ville inconnue").strip(),
                url=str(item.get("link") or "").strip(),
                available_rooms=parse_available_rooms(
                    extra.get("available_rooms"), residence_id
                ),
            )
        )
    return residences


def validate_expected_residences(
    residences: Iterable[Residence], expected_ids: frozenset[int]
) -> None:
    actual_ids = {residence.residence_id for residence in residences}
    missing = expected_ids - actual_ids
    if missing:
        missing_text = ", ".join(str(value) for value in sorted(missing))
        raise CheckerError(
            "Réponse incomplète : résidence(s) attendue(s) absente(s) : " + missing_text
        )


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS check_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checked_at TEXT NOT NULL,
            status TEXT NOT NULL,
            residence_count INTEGER,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS availability_history (
            run_id INTEGER NOT NULL REFERENCES check_runs(id),
            residence_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            city TEXT NOT NULL,
            url TEXT NOT NULL,
            available_rooms INTEGER NOT NULL,
            PRIMARY KEY (run_id, residence_id)
        );

        CREATE TABLE IF NOT EXISTS residence_state (
            residence_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            city TEXT NOT NULL,
            url TEXT NOT NULL,
            available_rooms INTEGER NOT NULL,
            last_checked_at TEXT NOT NULL
        );
        """
    )
    return connection


def record_success(
    connection: sqlite3.Connection,
    checked_at: str,
    residences: list[Residence],
) -> None:
    with connection:
        cursor = connection.execute(
            "INSERT INTO check_runs(checked_at, status, residence_count) VALUES (?, 'success', ?)",
            (checked_at, len(residences)),
        )
        run_id = int(cursor.lastrowid)
        connection.executemany(
            """
            INSERT INTO availability_history(
                run_id, residence_id, title, city, url, available_rooms
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    residence.residence_id,
                    residence.title,
                    residence.city,
                    residence.url,
                    residence.available_rooms,
                )
                for residence in residences
            ],
        )


def update_state(
    connection: sqlite3.Connection,
    checked_at: str,
    residences: Iterable[Residence],
) -> None:
    with connection:
        connection.executemany(
            """
            INSERT INTO residence_state(
                residence_id, title, city, url, available_rooms, last_checked_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(residence_id) DO UPDATE SET
                title = excluded.title,
                city = excluded.city,
                url = excluded.url,
                available_rooms = excluded.available_rooms,
                last_checked_at = excluded.last_checked_at
            """,
            [
                (
                    residence.residence_id,
                    residence.title,
                    residence.city,
                    residence.url,
                    residence.available_rooms,
                    checked_at,
                )
                for residence in residences
            ],
        )


def record_failure(
    connection: sqlite3.Connection, checked_at: str, error_message: str
) -> None:
    with connection:
        connection.execute(
            "INSERT INTO check_runs(checked_at, status, error) VALUES (?, 'error', ?)",
            (checked_at, error_message[:2000]),
        )


def format_availability_notification(
    residences: Iterable[Residence], checked_at: str
) -> str:
    available = [residence for residence in residences if residence.available_rooms > 0]
    total = sum(residence.available_rooms for residence in available)
    noun = "logement disponible" if total == 1 else "logements disponibles"
    lines = [
        f"ALERTE ARPEJ — {total} {noun}",
        f"Contrôle : {checked_at}",
    ]
    for residence in available:
        room_noun = "logement" if residence.available_rooms == 1 else "logements"
        lines.extend(
            [
                "",
                f"Résidence : {residence.title}",
                f"Ville : {residence.city}",
                f"Disponibilité : {residence.available_rooms} {room_noun}",
            ]
        )
        if residence.url:
            lines.append(f"Lien : {residence.url}")
    return "\n".join(lines)


def append_alert_file(data_directory: Path, checked_at: str, message: str) -> None:
    alert_path = data_directory / "availability_alerts.log"
    with alert_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{checked_at}]\n{message}\n\n")


def send_webhook(webhook_url: str, message: str, timeout_seconds: float) -> None:
    parsed = urlparse(webhook_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise CheckerError("ARPEJ_WEBHOOK_URL doit être une URL HTTPS valide")
    body = json.dumps({"content": message, "text": message}).encode("utf-8")
    request = Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds):
            pass
    except HTTPError as exc:
        raise CheckerError(
            f"Échec de la notification webhook (HTTP {exc.code})"
        ) from None
    except (URLError, TimeoutError, OSError):
        raise CheckerError("Échec réseau de la notification webhook") from None


def telegram_api_request(
    bot_token: str,
    method: str,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    if not bot_token or ":" not in bot_token or any(char.isspace() for char in bot_token):
        raise CheckerError("Le token Telegram est absent ou invalide")
    if not method.isalpha():
        raise CheckerError("Méthode Telegram invalide")

    request = Request(
        f"https://api.telegram.org/bot{bot_token}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            result = json.load(response)
    except HTTPError as exc:
        # L'URL d'une HTTPError contient le token : ne jamais journaliser exc.
        raise CheckerError(
            f"Échec de la notification Telegram (HTTP {exc.code})"
        ) from None
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        raise CheckerError("Échec réseau de la notification Telegram") from None

    if not isinstance(result, dict) or result.get("ok") is not True:
        description = "réponse API invalide"
        if isinstance(result, dict) and isinstance(result.get("description"), str):
            description = result["description"][:300]
        raise CheckerError(f"Telegram a refusé la requête : {description}")
    return result


def send_telegram(
    bot_token: str,
    chat_id: str,
    message: str,
    timeout_seconds: float,
) -> None:
    chat_id = chat_id.strip()
    if not chat_id:
        raise CheckerError("Le chat ID Telegram est absent")
    telegram_api_request(
        bot_token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout_seconds,
    )


def send_ntfy(topic_url: str, message: str, timeout_seconds: float) -> None:
    parsed = urlparse(topic_url)
    topic = parsed.path.strip("/")
    if (
        parsed.scheme != "https"
        or parsed.hostname != "ntfy.sh"
        or not (20 <= len(topic) <= 64)
        or any(char not in "-_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" for char in topic)
    ):
        raise CheckerError("L'URL de notification ntfy est invalide")
    request = Request(
        topic_url,
        data=message.encode("utf-8"),
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "Title": "ARPEJ - disponibilite detectee",
            "Priority": "high",
            "Tags": "house,rotating_light",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds):
            pass
    except HTTPError as exc:
        raise CheckerError(f"Échec de la notification ntfy (HTTP {exc.code})") from None
    except (URLError, TimeoutError, OSError):
        raise CheckerError("Échec réseau de la notification ntfy") from None


def discover_telegram_chats(
    bot_token: str, timeout_seconds: float
) -> list[tuple[str, str]]:
    response = telegram_api_request(
        bot_token,
        "getUpdates",
        {"limit": 50, "timeout": 0},
        timeout_seconds,
    )
    updates = response.get("result", [])
    if not isinstance(updates, list):
        raise CheckerError("Réponse getUpdates de Telegram invalide")

    chats: dict[str, str] = {}
    for update in updates:
        if not isinstance(update, dict):
            continue
        message = update.get("message") or update.get("channel_post")
        if not isinstance(message, dict) or not isinstance(message.get("chat"), dict):
            continue
        chat = message["chat"]
        chat_id = str(chat.get("id", "")).strip()
        if not chat_id:
            continue
        name_parts = [
            str(chat.get(key, "")).strip()
            for key in ("first_name", "last_name", "title", "username")
        ]
        chats[chat_id] = " ".join(part for part in name_parts if part) or "chat Telegram"
    return sorted(chats.items())


def send_configured_notifications(
    config: Config, message: str
) -> tuple[str, ...]:
    channels: list[str] = []
    secrets = load_notification_secrets(config.secrets_file)
    bot_token = notification_secret(
        secrets,
        config.telegram_bot_token_environment_variable,
        "telegram_bot_token",
    )
    chat_id = notification_secret(
        secrets,
        config.telegram_chat_id_environment_variable,
        "telegram_chat_id",
    )
    if bool(bot_token) != bool(chat_id):
        raise CheckerError(
            "Telegram est partiellement configuré : le token et le chat ID sont requis"
        )
    if bot_token and chat_id:
        send_telegram(bot_token, chat_id, message, config.timeout_seconds)
        channels.append("Telegram")

    ntfy_topic_url = notification_secret(
        secrets,
        config.ntfy_topic_url_environment_variable,
        "ntfy_topic_url",
    )
    if ntfy_topic_url:
        send_ntfy(ntfy_topic_url, message, config.timeout_seconds)
        channels.append("ntfy")

    webhook_url = notification_secret(
        secrets,
        config.webhook_url_environment_variable,
        "webhook_url",
    )
    if webhook_url:
        send_webhook(webhook_url, message, config.timeout_seconds)
        channels.append("webhook")
    return tuple(channels)


def load_notification_secrets(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckerError(f"Fichier de secrets invalide : {path.name}") from exc
    if not isinstance(raw, dict):
        raise CheckerError(f"Fichier de secrets invalide : {path.name}")
    return {
        str(key): str(value).strip()
        for key, value in raw.items()
        if isinstance(value, (str, int))
    }


def notification_secret(
    secrets: dict[str, str], environment_name: str, file_key: str
) -> str:
    return os.environ.get(environment_name, "").strip() or secrets.get(file_key, "")


def configure_logging(data_directory: Path) -> logging.Logger:
    data_directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("arpej_checker")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    log_file = RotatingFileHandler(
        data_directory / "arpej_checker.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    log_file.setFormatter(formatter)
    logger.addHandler(log_file)
    return logger


def print_summary(residences: list[Residence]) -> None:
    total = sum(residence.available_rooms for residence in residences)
    print(
        f"Contrôle ARPEJ terminé : {len(residences)} résidence(s), "
        f"{total} logement(s) disponible(s)."
    )
    for residence in residences:
        marker = "DISPONIBLE" if residence.available_rooms > 0 else "complet"
        print(
            f"- {residence.title} ({residence.city}) : "
            f"{residence.available_rooms} — {marker}"
        )


def run(config: Config, logger: logging.Logger) -> int:
    checked_at = utc_now()
    checked_at_display = datetime.now().astimezone().strftime("%d/%m/%Y à %H:%M:%S")
    database_path = config.data_directory / "arpej_history.sqlite3"
    connection = open_database(database_path)
    try:
        payload = fetch_payload(config)
        residences = parse_residences(payload)
        validate_expected_residences(residences, config.expected_residence_ids)
        print_summary(residences)

        available = [
            residence for residence in residences if residence.available_rooms > 0
        ]
        if available:
            message = format_availability_notification(
                available, checked_at_display
            )
            print(f"\n{message}")
            append_alert_file(config.data_directory, checked_at, message)
            channels = send_configured_notifications(config, message)
            if channels:
                details = ", ".join(
                    f"{residence.title} ({residence.available_rooms})"
                    for residence in available
                )
                logger.info(
                    "Décision notification : envoyée via %s ; disponibilité(s) : %s",
                    ", ".join(channels),
                    details,
                )
            else:
                logger.warning(
                    "Décision notification : disponibilité détectée, mais aucun canal "
                    "distant n'est configuré"
                )
        else:
            logger.info(
                "Décision notification : non envoyée ; aucun logement disponible "
                "sur %s résidences",
                len(residences),
            )

        record_success(connection, checked_at, residences)
        update_state(connection, checked_at, residences)
        logger.info("Contrôle réussi pour %s résidences", len(residences))
        return 0
    except Exception as exc:
        record_failure(connection, checked_at, str(exc))
        logger.error("Contrôle en échec : %s", exc)
        return 1
    finally:
        connection.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vérifie les disponibilités des résidences ARPEJ sélectionnées."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Fichier de configuration (défaut : {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--test-notification",
        action="store_true",
        help="Envoie immédiatement un message de test sur les canaux configurés.",
    )
    parser.add_argument(
        "--show-telegram-chat-id",
        action="store_true",
        help="Affiche les chats ayant récemment écrit au bot Telegram.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Effectue le contrôle même en dehors de la plage horaire active.",
    )
    return parser.parse_args(argv)


def test_notification(config: Config, logger: logging.Logger) -> int:
    try:
        channels = send_configured_notifications(
            config,
            "Test ARPEJ réussi : les notifications de disponibilité sont actives.",
        )
        if not channels:
            raise CheckerError("Aucun canal de notification n'est configuré")
        logger.info("Test envoyé via %s", ", ".join(channels))
        print("Notification de test envoyée avec succès.")
        return 0
    except Exception as exc:
        logger.error("Test de notification en échec : %s", exc)
        return 1


def show_telegram_chat_ids(config: Config, logger: logging.Logger) -> int:
    secrets = load_notification_secrets(config.secrets_file)
    token = notification_secret(
        secrets,
        config.telegram_bot_token_environment_variable,
        "telegram_bot_token",
    )
    if not token:
        logger.error(
            "La variable %s n'est pas définie",
            config.telegram_bot_token_environment_variable,
        )
        return 1
    try:
        chats = discover_telegram_chats(token, config.timeout_seconds)
    except Exception as exc:
        logger.error("Lecture des chats Telegram en échec : %s", exc)
        return 1
    if not chats:
        logger.error("Aucun chat trouvé. Envoyez d'abord /start à votre bot Telegram.")
        return 1
    print("Chats Telegram trouvés :")
    for chat_id, name in chats:
        print(f"- {chat_id} — {name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config.resolve())
        logger = configure_logging(config.data_directory)
    except Exception as exc:
        print(f"Erreur de configuration : {exc}", file=sys.stderr)
        return 2
    if args.show_telegram_chat_id:
        return show_telegram_chat_ids(config, logger)
    if args.test_notification:
        return test_notification(config, logger)
    if not args.force and not is_within_active_hours(config):
        logger.info(
            "Contrôle ignoré : heure locale hors plage active %02dh00–%02dh59",
            config.active_start_hour,
            config.active_end_hour,
        )
        return 0
    return run(config, logger)


if __name__ == "__main__":
    raise SystemExit(main())
