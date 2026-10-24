from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from arpej_checker import CheckerError, DEFAULT_CONFIG_PATH
from configure_residences import city_ids_from_search_url, main


SEARCH_URL = "https://www.arpej.fr/fr/nos-residences/?related_city=123%2C456&show_if_full=true"
PAYLOAD = {"residences": [
    {"ID": 1, "title": "One", "extra_data": {"city": "Paris", "available_rooms": 0}},
    {"ID": 2, "title": "Two", "extra_data": {"city": "Paris", "available_rooms": 2}},
]}


class ConfigureResidencesTests(unittest.TestCase):
    def test_extracts_comma_separated_city_ids(self):
        self.assertEqual(("123", "456"), city_ids_from_search_url(SEARCH_URL))

    def test_extracts_array_city_ids_without_duplicates(self):
        url = "https://arpej.fr/fr/nos-residences/?related_city[]=123&related_city[]=456&related_city[]=123"
        self.assertEqual(("123", "456"), city_ids_from_search_url(url))

    def test_rejects_other_websites_and_invalid_cities(self):
        for url in (
            SEARCH_URL.replace("www.arpej.fr", "example.test"),
            SEARCH_URL.replace("https:", "http:"),
            SEARCH_URL.replace("nos-residences", "residence/test"),
            "https://www.arpej.fr/fr/nos-residences/",
            "https://www.arpej.fr/fr/nos-residences/?related_city=not-a-number",
        ):
            with self.subTest(url=url), self.assertRaises(CheckerError):
                city_ids_from_search_url(url)

    def run_setup(self, extra_args, payload=PAYLOAD):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
            path.write_text(original, encoding="utf-8")
            with (
                patch("configure_residences.fetch_payload", return_value=payload),
                redirect_stdout(StringIO()),
                redirect_stderr(StringIO()),
            ):
                result = main([SEARCH_URL, "--config", str(path), *extra_args])
            return result, json.loads(original), json.loads(path.read_text(encoding="utf-8"))

    def test_preview_does_not_change_config(self):
        result, original, after = self.run_setup([])
        self.assertEqual(0, result)
        self.assertEqual(original, after)

    def test_write_selects_all_results_by_default(self):
        result, original, after = self.run_setup(["--write"])
        self.assertEqual(0, result)
        original.update(city_ids=["123", "456"], expected_residence_ids=[1, 2])
        self.assertEqual(original, after)

    def test_write_can_select_a_subset(self):
        result, _, after = self.run_setup(["--residence-ids", "2", "--write"])
        self.assertEqual(0, result)
        self.assertEqual([2], after["expected_residence_ids"])

    def test_missing_selected_id_preserves_config(self):
        result, original, after = self.run_setup(["--residence-ids", "99", "--write"])
        self.assertEqual(1, result)
        self.assertEqual(original, after)

    def test_empty_results_preserve_config(self):
        result, original, after = self.run_setup(["--write"], {"residences": []})
        self.assertEqual(1, result)
        self.assertEqual(original, after)

    def test_network_failure_preserves_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
            path.write_text(original, encoding="utf-8")
            with (
                patch("configure_residences.fetch_payload", side_effect=CheckerError("network failure")),
                redirect_stderr(StringIO()),
            ):
                self.assertEqual(1, main([SEARCH_URL, "--config", str(path), "--write"]))
            self.assertEqual(original, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
