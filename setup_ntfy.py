#!/usr/bin/env python3
"""Configure un sujet ntfy aléatoire et envoie une notification de test."""

from __future__ import annotations

import json
import os
import secrets as secrets_module

from arpej_checker import (
    DEFAULT_CONFIG_PATH,
    load_config,
    load_notification_secrets,
    send_ntfy,
)


def main() -> int:
    config = load_config(DEFAULT_CONFIG_PATH)
    notification_secrets = load_notification_secrets(config.secrets_file)
    topic_url = notification_secrets.get("ntfy_topic_url", "")
    if not topic_url:
        topic = "arpej-" + secrets_module.token_urlsafe(32)
        topic_url = f"https://ntfy.sh/{topic}"
        notification_secrets["ntfy_topic_url"] = topic_url
        config.secrets_file.write_text(
            json.dumps(notification_secrets, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            os.chmod(config.secrets_file, 0o600)
        except OSError:
            pass

    send_ntfy(
        topic_url,
        "Test ARPEJ reussi : les notifications de disponibilite sont actives.",
        config.timeout_seconds,
    )
    topic = topic_url.rsplit("/", 1)[-1]
    print("Notification ntfy de test envoyee.")
    print(f"WEB_URL={topic_url}")
    print(f"APP_URL=ntfy://ntfy.sh/{topic}?display=Alertes+ARPEJ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
