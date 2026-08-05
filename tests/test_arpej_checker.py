from pathlib import Path
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arpej_checker import (  # noqa: E402
    Config,
    CheckerError,
    Residence,
    already_succeeded_this_hour,
    build_api_url,
    evaluate_scheduler_gate,
    format_availability_notification,
    is_within_active_hours,
    load_scheduler_state,
    mark_hour_as_successful,
    parse_residences,
    run,
    run_once_per_hour,
    send_configured_notifications,
    send_ntfy,
    send_telegram,
    validate_expected_residences,
)


class ArpejCheckerTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            api_url="https://www.arpej.fr/wp-json/sn/residences",
            city_ids=("123", "456"),
            expected_residence_ids=frozenset({1}),
            timeout_seconds=20,
            retries=3,
            active_start_hour=8,
            active_end_hour=18,
            data_directory=Path("data"),
            secrets_file=Path("secrets.json"),
            ntfy_topic_url_environment_variable="ARPEJ_NTFY_TOPIC_URL",
            webhook_url_environment_variable="ARPEJ_WEBHOOK_URL",
            telegram_bot_token_environment_variable="ARPEJ_TELEGRAM_BOT_TOKEN",
            telegram_chat_id_environment_variable="ARPEJ_TELEGRAM_CHAT_ID",
        )

    def test_build_api_url_keeps_every_city_id(self):
        config = self.config

        url = build_api_url(config)

        self.assertIn("related_city%5B%5D=123", url)
        self.assertIn("related_city%5B%5D=456", url)
        self.assertIn("show_if_full=true", url)

    def test_parse_residences_extracts_available_rooms(self):
        payload = {
            "residences": [
                {
                    "ID": 42,
                    "title": "Résidence test",
                    "link": "https://www.arpej.fr/fr/residence/test/",
                    "extra_data": {"city": "Paris", "available_rooms": 2},
                }
            ]
        }

        residence = parse_residences(payload)[0]

        self.assertEqual(42, residence.residence_id)
        self.assertEqual(2, residence.available_rooms)
        self.assertEqual("Résidence test", residence.title)

    def test_missing_expected_residence_is_rejected(self):
        residence = Residence(1, "Test", "Paris", "https://example.test", 0)
        with self.assertRaises(CheckerError):
            validate_expected_residences([residence], frozenset({1, 2}))

    def test_availability_message_contains_exact_residence_details(self):
        residence = Residence(
            42,
            "Claudie Haigneré - Palaiseau",
            "Palaiseau",
            "https://www.arpej.fr/fr/residence/claudie-haignere-palaiseau/",
            2,
        )

        message = format_availability_notification(
            [residence], "03/08/2026 à 10:00:00"
        )

        self.assertIn("Claudie Haigneré - Palaiseau", message)
        self.assertIn("Ville : Palaiseau", message)
        self.assertIn("Disponibilité : 2 logements", message)
        self.assertIn(residence.url, message)

    def test_active_hours_are_inclusive(self):
        self.assertTrue(is_within_active_hours(self.config, datetime(2026, 8, 3, 8)))
        self.assertTrue(is_within_active_hours(self.config, datetime(2026, 8, 3, 18)))
        self.assertFalse(is_within_active_hours(self.config, datetime(2026, 8, 3, 19)))

    def test_run_notifies_on_every_check_while_available(self):
        payload = {
            "residences": [
                {
                    "ID": 42,
                    "title": "Résidence disponible",
                    "link": "https://www.arpej.fr/fr/residence/test/",
                    "extra_data": {"city": "Paris", "available_rooms": 1},
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp_directory:
            config = replace(
                self.config,
                expected_residence_ids=frozenset({42}),
                data_directory=Path(temp_directory),
                secrets_file=Path(temp_directory) / "secrets.json",
            )
            logger = Mock()
            with (
                patch("arpej_checker.fetch_payload", return_value=payload),
                patch(
                    "arpej_checker.send_configured_notifications",
                    return_value=("test",),
                ) as send_notification,
            ):
                self.assertEqual(0, run(config, logger))
                self.assertEqual(0, run(config, logger))

        self.assertEqual(2, send_notification.call_count)
        sent_message = send_notification.call_args.args[1]
        self.assertIn("Résidence : Résidence disponible", sent_message)
        self.assertIn("Disponibilité : 1 logement", sent_message)

    def test_hourly_lock_skips_second_successful_attempt(self):
        current_time = datetime(2026, 8, 5, 10, 7, tzinfo=timezone(timedelta(hours=2)))
        with tempfile.TemporaryDirectory() as temp_directory:
            state_path = Path(temp_directory) / "scheduler_state.json"
            logger = Mock()
            with patch("arpej_checker.run", return_value=0) as mocked_run:
                first_result = run_once_per_hour(
                    self.config, logger, state_path, current_time
                )
                second_result = run_once_per_hour(
                    self.config,
                    logger,
                    state_path,
                    current_time.replace(minute=37),
                )

        self.assertEqual(0, first_result)
        self.assertEqual(0, second_result)
        mocked_run.assert_called_once_with(self.config, logger)

    def test_hourly_lock_allows_the_next_hour(self):
        current_time = datetime(2026, 8, 5, 10, 7, tzinfo=timezone(timedelta(hours=2)))
        with tempfile.TemporaryDirectory() as temp_directory:
            state_path = Path(temp_directory) / "scheduler_state.json"
            mark_hour_as_successful(state_path, current_time)

            self.assertTrue(already_succeeded_this_hour(state_path, current_time))
            self.assertFalse(
                already_succeeded_this_hour(
                    state_path, current_time + timedelta(hours=1)
                )
            )

    def test_failed_check_does_not_lock_the_hour(self):
        current_time = datetime(2026, 8, 5, 10, 7, tzinfo=timezone(timedelta(hours=2)))
        with tempfile.TemporaryDirectory() as temp_directory:
            state_path = Path(temp_directory) / "scheduler_state.json"
            logger = Mock()
            with patch("arpej_checker.run", return_value=1):
                result = run_once_per_hour(
                    self.config, logger, state_path, current_time
                )

            state = load_scheduler_state(state_path)

        self.assertEqual(1, result)
        self.assertIsNone(state["last_successful_hour"])

    def test_scheduler_gate_opens_unchecked_active_hour(self):
        current_time = datetime(2026, 8, 5, 10, 7, tzinfo=timezone(timedelta(hours=2)))
        with tempfile.TemporaryDirectory() as temp_directory:
            state_path = Path(temp_directory) / "scheduler_state.json"

            should_check, reason = evaluate_scheduler_gate(
                self.config, state_path, current_time
            )

        self.assertTrue(should_check)
        self.assertIn("est ouvert", reason)

    def test_scheduler_gate_skips_locked_hour_without_running_checker(self):
        current_time = datetime(2026, 8, 5, 10, 7, tzinfo=timezone(timedelta(hours=2)))
        with tempfile.TemporaryDirectory() as temp_directory:
            state_path = Path(temp_directory) / "scheduler_state.json"
            mark_hour_as_successful(state_path, current_time)

            should_check, reason = evaluate_scheduler_gate(
                self.config, state_path, current_time.replace(minute=52)
            )

        self.assertFalse(should_check)
        self.assertIn("déjà verrouillé", reason)

    def test_scheduler_gate_skips_outside_active_hours(self):
        current_time = datetime(2026, 8, 5, 19, 5, tzinfo=timezone(timedelta(hours=2)))
        with tempfile.TemporaryDirectory() as temp_directory:
            state_path = Path(temp_directory) / "scheduler_state.json"

            should_check, reason = evaluate_scheduler_gate(
                self.config, state_path, current_time
            )

        self.assertFalse(should_check)
        self.assertIn("hors plage active", reason)

    def test_send_telegram_uses_chat_id_and_message(self):
        response = BytesIO(b'{"ok": true, "result": {"message_id": 1}}')
        with patch("arpej_checker.urlopen", return_value=response) as mocked_open:
            send_telegram("123456:secret-token", "987654", "Alerte test", 20)

        request = mocked_open.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual("987654", body["chat_id"])
        self.assertEqual("Alerte test", body["text"])
        self.assertIn("/sendMessage", request.full_url)

    def test_send_ntfy_posts_high_priority_message(self):
        response = BytesIO(b'{"id": "test"}')
        with patch("arpej_checker.urlopen", return_value=response) as mocked_open:
            send_ntfy(
                "https://ntfy.sh/arpej-0123456789abcdefghijklmnop",
                "Un logement est disponible",
                20,
            )

        request = mocked_open.call_args.args[0]
        self.assertEqual(b"Un logement est disponible", request.data)
        self.assertEqual("high", request.headers["Priority"])
        self.assertEqual("POST", request.method)

    def test_ntfy_topic_can_come_from_github_environment(self):
        topic_url = "https://ntfy.sh/arpej-0123456789abcdefghijklmnop"
        with (
            patch.dict(os.environ, {"ARPEJ_NTFY_TOPIC_URL": topic_url}, clear=False),
            patch("arpej_checker.send_ntfy") as mocked_send,
        ):
            channels = send_configured_notifications(self.config, "Test cloud")

        self.assertEqual(("ntfy",), channels)
        mocked_send.assert_called_once_with(topic_url, "Test cloud", 20)




if __name__ == "__main__":
    unittest.main()
