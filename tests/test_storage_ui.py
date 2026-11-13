import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StorageUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    def test_storage_controls_are_real_buttons_and_dialog(self):
        self.assertIn('id="storage"', self.html)
        self.assertIn('id="vault-name" aria-haspopup="dialog"', self.html)
        self.assertIn('id="storage-dialog"', self.html)
        self.assertIn('id="vault-folder" webkitdirectory multiple', self.html)
        self.assertIn('id="example-storage"', self.html)
        self.assertIn('id="edit-dialog"', self.html)

    def test_top_actions_are_one_accessible_compact_toolbar(self):
        self.assertIn('class="actions" role="toolbar"', self.html)
        self.assertIn('class="action-group"', self.html)
        self.assertIn('class="action-icon"', self.html)
        self.assertIn('class="top-views"', self.html)
        self.assertNotIn("$('view-crumb')", self.js)

    def test_folder_import_uses_existing_create_only_endpoints(self):
        self.assertIn("'/api/notes'", self.js)
        self.assertIn("'/api/images'", self.js)
        self.assertIn("error.message==='already_exists'", self.js)
        self.assertNotIn("method:'DELETE'", self.js)
        self.assertNotIn('confirm(', self.js)

    def test_example_and_editor_use_authenticated_api(self):
        self.assertIn('async function addExample()', self.js)
        self.assertIn('async function ensureWritable()', self.js)
        self.assertIn("$('storage-progress').textContent=failure(error)", self.js)
        self.assertIn("Examples/Storage-import-example.md", self.js)
        self.assertIn("'/api/notes/update'", self.js)
        self.assertIn("method:'PUT'", self.js)
        self.assertIn('async function openEditor(note)', self.js)

    def test_storage_copy_is_separate_from_server_mount(self):
        self.assertIn("storageExplanation", self.js)
        self.assertIn("/vault", self.js)
        self.assertNotIn("showDirectoryPicker", self.js)

    def test_storage_opens_as_default_on_first_start(self):
        self.assertIn("function openStorageOnStart()", self.js)
        self.assertIn("sessionStorage.getItem('c-obsidian-storage-started')", self.js)
        self.assertIn("openStorageOnStart();", self.js)


if __name__ == "__main__":
    unittest.main()
