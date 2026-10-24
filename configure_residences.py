#!/usr/bin/env python3
"""Preview or save an ARPEJ watchlist from a residence-search URL."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse

from arpej_checker import (
    CheckerError,
    DEFAULT_CONFIG_PATH,
    fetch_payload,
    load_config,
    parse_residences,
    validate_expected_residences,
)


def city_ids_from_search_url(search_url: str) -> tuple[str, ...]:
    parsed = urlparse(search_url)
    if (
        parsed.scheme != "https"
        or parsed.netloc not in {"arpej.fr", "www.arpej.fr"}
        or parsed.path.rstrip("/") != "/fr/nos-residences"
    ):
        raise CheckerError("Use an https://www.arpej.fr/fr/nos-residences/ search URL")
    query = parse_qs(parsed.query)
    values = query.get("related_city", []) + query.get("related_city[]", [])
    city_ids = tuple(
        dict.fromkeys(part.strip() for value in values for part in value.split(","))
    )
    if not city_ids or any(not value.isascii() or not value.isdigit() for value in city_ids):
        raise CheckerError("The URL must contain numeric related_city city IDs")
    return city_ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("search_url", help="Copy the URL after selecting cities on ARPEJ")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument(
        "--residence-ids", nargs="+", type=int,
        help="Only watch these IDs; default: all listed residences",
    )
    parser.add_argument(
        "--write", action="store_true",
        help="Save the watchlist in config.json (default: preview only)",
    )
    args = parser.parse_args(argv)
    try:
        city_ids = city_ids_from_search_url(args.search_url)
        config = replace(load_config(args.config.resolve()), city_ids=city_ids)
        residences = parse_residences(fetch_payload(config))
        if not residences:
            raise CheckerError("No residences found; the configuration was not changed")
        selected_ids = (
            frozenset(args.residence_ids) if args.residence_ids else
            frozenset(residence.residence_id for residence in residences)
        )
        validate_expected_residences(residences, selected_ids)
        print("ARPEJ residences (* = selected):")
        for residence in residences:
            marker = "*" if residence.residence_id in selected_ids else " "
            print(
                f"{marker} {residence.residence_id}: {residence.title} — "
                f"{residence.city} ({residence.available_rooms} available)"
            )
        selection = {
            "city_ids": list(city_ids),
            "expected_residence_ids": sorted(selected_ids),
        }
        print(json.dumps(selection, ensure_ascii=False, indent=2))
        print("Only cities are imported from the URL; use residence IDs to choose the exact watchlist.")
        if args.write:
            raw = json.loads(args.config.read_text(encoding="utf-8"))
            raw.update(selection)
            args.config.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(f"Saved {len(selected_ids)} residence(s) in {args.config.name}. Commit this file to your own repository.")
        else:
            print("Preview only: no files changed and no notifications sent. Add --write to save.")
        return 0
    except (CheckerError, OSError, ValueError) as exc:
        print(f"Configuration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
