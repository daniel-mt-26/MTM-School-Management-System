from django.test import SimpleTestCase


class LocalFrontendCorsTests(SimpleTestCase):
    def test_health_get_allows_each_local_vite_origin(self):
        for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
            with self.subTest(origin=origin):
                response = self.client.get("/api/health/", HTTP_ORIGIN=origin)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Access-Control-Allow-Origin"], origin)
