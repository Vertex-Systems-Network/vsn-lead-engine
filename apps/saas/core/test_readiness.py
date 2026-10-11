"""Private readiness tests run with a mocked database and no provider access."""

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


class InternalReadinessTests(SimpleTestCase):
    url = "/internal/readiness/"

    @override_settings(SAAS_INTERNAL_READINESS_ENABLED=False)
    def test_disabled_is_not_found_without_database_probe(self):
        with patch("core.readiness.connections") as connections:
            self.assertEqual(self.client.get(self.url).status_code, 404)
            self.assertEqual(self.client.post(self.url).status_code, 404)
            connections.__getitem__.assert_not_called()

    @override_settings(SAAS_INTERNAL_READINESS_ENABLED=True)
    def test_ready_is_one_readonly_query_and_never_cached(self):
        with patch("core.readiness.connections") as connections:
            cursor = connections.__getitem__.return_value.cursor.return_value
            cursor.__enter__.return_value.fetchone.return_value = (1,)
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready"})
        self.assertIn("no-store", response["Cache-Control"])
        cursor.__enter__.return_value.execute.assert_called_once_with("SELECT 1")

    @override_settings(SAAS_INTERNAL_READINESS_ENABLED=True)
    def test_database_unavailable_is_generic_503(self):
        with patch("core.readiness.connections") as connections:
            connections.__getitem__.side_effect = RuntimeError(
                "password=synthetic-should-never-leak"
            )
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotIn("synthetic-should-never-leak", response.content.decode())

    @override_settings(SAAS_INTERNAL_READINESS_ENABLED=True)
    def test_nonready_row_and_non_get_method_fail_closed(self):
        with patch("core.readiness.connections") as connections:
            cursor = connections.__getitem__.return_value.cursor.return_value
            cursor.__enter__.return_value.fetchone.return_value = None
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"status": "unavailable"})
            self.assertEqual(self.client.post(self.url).status_code, 405)
            self.assertEqual(self.client.head(self.url).status_code, 405)
            self.assertEqual(cursor.__enter__.return_value.execute.call_count, 1)
