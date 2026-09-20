from pathlib import Path
from unittest.mock import patch

from backend import examples
from backend.tests.test_api import ApiTestCase
from data_collector import dataset


class BusinessWorkspaceTests(ApiTestCase):
    def test_default_workspace_does_not_expose_academic_routes(self):
        dataset.ensure_dataset_file()
        before = Path(dataset.DATASET_PATH).read_bytes()
        for path in (
            "/api/coursework", "/api/coursework/export", "/api/coursework/screenshots",
            "/api/examples",
        ):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        self.assertEqual(
            self.client.put("/api/coursework/project", json={"group_members": ["", "", ""]}).status_code,
            404,
        )
        schema = self.client.get("/openapi.json").json()
        self.assertFalse(any(path.startswith(("/api/coursework", "/api/examples")) for path in schema["paths"]))
        self.assertEqual(schema["info"]["title"], "Mboa Language Workspace")
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), before)
        self.assertEqual(self.requests, [])

    def test_disabled_practice_sources_are_rejected_without_loading_or_cloud_processing(self):
        with patch.object(examples, "load_examples", side_effect=AssertionError("Must not load archived data")):
            for path, data in (
                ("/api/translate", {"text": "Constructed example", "use_examples": True}),
                ("/api/chat", {"message": "Constructed example", "use_examples": True}),
            ):
                response = self.client.post(path, json=data)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn("not available", response.json()["detail"])
        self.assertEqual(self.requests, [])

    def test_business_categories_support_creation_and_global_review_counts(self):
        metadata = self.client.get("/api/metadata").json()
        self.assertEqual(metadata["categories"], dataset.BUSINESS_CATEGORIES)
        self.assertNotIn("Campus Life", metadata["categories"])
        for text, category, status in (
            ("Customer greeting", "Customer Service", "approved"),
            ("Delivery instruction", "Logistics", "unreviewed"),
        ):
            response = self.client.post("/api/dataset", json={
                "text": text, "category": category, "review_status": status, "language": "francanglais",
            })
            self.assertEqual(response.status_code, 201, response.text)
        response = self.client.get("/api/dataset?query=Customer").json()
        self.assertEqual(len(response["entries"]), 1)
        self.assertEqual(response["total"], 2)
        self.assertEqual(response["by_review_status"], {"approved": 1, "unreviewed": 1})

    def test_existing_categories_and_original_metadata_are_preserved(self):
        legacy = self.client.post("/api/dataset", json={
            "text": "Original term", "category": "Campus Life", "notes": "Original source note",
            "contributor": "Known contributor", "language": "francanglais",
        }).json()
        response = self.client.patch(f"/api/dataset/{legacy['id']}", json={"english_gloss": "Updated meaning"})
        self.assertEqual(response.status_code, 200, response.text)
        updated = response.json()
        for field in ("category", "notes", "contributor", "text"):
            self.assertEqual(updated[field], legacy[field])
