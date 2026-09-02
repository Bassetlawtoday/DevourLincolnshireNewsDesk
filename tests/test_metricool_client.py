import unittest
from unittest.mock import patch

from newsdesk.social.metricool import MetricoolClient, MetricoolError, MetricoolImageError


class MetricoolClientTests(unittest.TestCase):
    def test_connection_details_exposes_facebook_profile(self):
        client = MetricoolClient(token="token", user_id="10")
        with patch.object(client, "list_brands", return_value=[{"id": 22, "userId": 10, "label": "Devour", "facebook": "Devour Lincolnshire", "timezone": "Europe/London"}]):
            brands = client.connection_details()
        self.assertEqual(brands[0]["id"], "22")
        self.assertEqual(brands[0]["networks"]["facebook"], "Devour Lincolnshire")

    def test_image_is_normalised_before_draft_creation(self):
        client = MetricoolClient(token="token", user_id="10", blog_id="22")
        calls = []
        def request(method, path, *, query=None, body=None):
            calls.append((method, path, query, body))
            return "https://metricool.test/image.jpg" if path == "/actions/normalize/image/url" else {"id": 99}
        with patch.object(client, "_request", side_effect=request):
            result = client.create_draft(text="Post", providers=["facebook"], publication_datetime="2026-09-02T13:00:00", timezone="Europe/London", image_url="https://source.test/image.jpg")
        self.assertEqual(result["id"], 99)
        self.assertEqual(calls[-1][3]["media"], ["https://metricool.test/image.jpg"])
        self.assertTrue(calls[-1][3]["draft"])
        self.assertFalse(calls[-1][3]["autoPublish"])

    def test_nested_draft_id_is_recognised(self):
        self.assertEqual(MetricoolClient.draft_id({"data": {"id": 123}}), "123")

    def test_local_image_is_uploaded_before_draft_creation(self):
        client = MetricoolClient(token="token", user_id="10", blog_id="22")
        calls = []
        with patch.object(client, "upload_local_image", return_value="https://metricool.test/local.jpg") as upload, patch.object(
            client, "_request", side_effect=lambda method, path, *, query=None, body=None: calls.append((method, path, query, body)) or {"id": 100}
        ):
            result = client.create_draft(
                text="Post", providers=["facebook"], publication_datetime="2026-09-02T13:00:00",
                timezone="Europe/London", image_path=r"C:\Images\chosen.jpg",
            )
        upload.assert_called_once_with(r"C:\Images\chosen.jpg")
        self.assertEqual(result["id"], 100)
        self.assertEqual(calls[-1][3]["media"], ["https://metricool.test/local.jpg"])
        self.assertFalse(calls[-1][3]["saveExternalMediaFiles"])

    def test_public_image_failure_is_identified_as_an_image_error(self):
        client = MetricoolClient(token="token", user_id="10", blog_id="22")
        with patch.object(client, "_request", side_effect=MetricoolError("timed out")):
            with self.assertRaisesRegex(MetricoolImageError, "timed out"):
                client.normalize_image("https://source.test/image.jpg")


if __name__ == "__main__":
    unittest.main()
