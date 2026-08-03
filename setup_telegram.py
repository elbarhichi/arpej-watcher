#!/usr/bin/env python3
"""Assistant interactif de configuration des notifications Telegram."""

from __future__ import annotations

from getpass import getpass
import json
import os
from pathlib import Path
import sys

from arpej_checker import (
    CheckerError,
    DEFAULT_CONFIG_PATH,
    discover_telegram_chats,
    load_config,
    load_notification_secrets,
    send_telegram,
)


def main() -> int:
    config = load_config(DEFAULT_CONFIG_PATH)
    print("Configuration Telegram pour le checker ARPEJ")
    bot_token = getpass("Collez le token donne par BotFather (saisie masquee) : ").strip()
    if not bot_token:
        raise CheckerError("Le token Telegram ne peut pas etre vide")

    input(
        "Dans Telegram, ouvrez votre nouveau bot, envoyez /start, "
        "puis appuyez sur Entree ici..."
    )
    chats = discover_telegram_chats(bot_token, config.timeout_seconds)
    if not chats:
        raise CheckerError(
            "Aucun chat trouve. Verifiez que /start a bien ete envoye au bon bot."
        )

    print("Chats trouves :")
    for chat_id, name in chats:
        print(f"- {chat_id} — {name}")

    default_chat_id = chats[0][0] if len(chats) == 1 else ""
    prompt = "Chat ID a utiliser"
    if default_chat_id:
        prompt += f" [{default_chat_id}]"
    selected_chat_id = input(prompt + " : ").strip() or default_chat_id
    known_ids = {chat_id for chat_id, _ in chats}
    if selected_chat_id not in known_ids:
        raise CheckerError("Le chat ID choisi ne figure pas dans la liste affichee")

    send_telegram(
        bot_token,
        selected_chat_id,
        "Test ARPEJ reussi : les notifications de disponibilite sont actives.",
        config.timeout_seconds,
    )

    secrets = load_notification_secrets(config.secrets_file)
    secrets["telegram_bot_token"] = bot_token
    secrets["telegram_chat_id"] = selected_chat_id
    config.secrets_file.write_text(
        json.dumps(secrets, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(config.secrets_file, 0o600)
    except OSError:
        pass

    print("Notification de test envoyee.")
    print(f"Configuration enregistree localement dans {config.secrets_file.name}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CheckerError, OSError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        raise SystemExit(1)
