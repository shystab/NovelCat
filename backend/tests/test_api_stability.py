from __future__ import annotations

import unittest
from contextlib import ExitStack
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.db.session import get_session
from app.main import app
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


class ApiStabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        def test_session():
            with Session(cls.engine) as session:
                yield session

        app.dependency_overrides[get_session] = test_session
        cls.original_auth_required = settings.AUTH_REQUIRED
        cls.original_app_access_token = settings.APP_ACCESS_TOKEN
        cls.original_deepseek_key = settings.DEEPSEEK_API_KEY
        cls.original_openai_key = settings.OPENAI_API_KEY
        cls.original_workspace_dir = settings.NOVEL_WORKSPACE_DIR
        cls.test_workspace = TemporaryDirectory()
        settings.AUTH_REQUIRED = True
        settings.APP_ACCESS_TOKEN = None
        settings.DEEPSEEK_API_KEY = None
        settings.OPENAI_API_KEY = None
        settings.NOVEL_WORKSPACE_DIR = cls.test_workspace.name
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        app.dependency_overrides.clear()
        settings.AUTH_REQUIRED = cls.original_auth_required
        settings.APP_ACCESS_TOKEN = cls.original_app_access_token
        settings.DEEPSEEK_API_KEY = cls.original_deepseek_key
        settings.OPENAI_API_KEY = cls.original_openai_key
        settings.NOVEL_WORKSPACE_DIR = cls.original_workspace_dir
        cls.test_workspace.cleanup()
        cls.engine.dispose()

    def setUp(self) -> None:
        SQLModel.metadata.drop_all(self.engine)
        SQLModel.metadata.create_all(self.engine)
        self.patches = ExitStack()
        self.patches.enter_context(patch("app.api.v1.endpoints.books.write_project_manifest"))
        self.patches.enter_context(patch("app.api.v1.endpoints.books.write_chapter_file"))
        self.patches.enter_context(patch("app.api.v1.endpoints.books.delete_chapter_files"))
        # API tests use an in-memory database. Background workers otherwise
        # open the real database and can invoke a configured external model.
        self.patches.enter_context(patch("app.api.v1.endpoints.chapters.generate_chapter_summary_background"))

    def tearDown(self) -> None:
        self.patches.close()

    def register(self, username: str, invite_code: str | None = None) -> dict:
        payload = {"username": username, "password": "password-123"}
        if invite_code:
            payload["invite_code"] = invite_code
        response = self.client.post("/api/v1/auth/register", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    @staticmethod
    def auth_headers(auth: dict) -> dict[str, str]:
        return {"Authorization": f"Bearer {auth['access_token']}"}

    def create_invited_user(self) -> tuple[dict, dict]:
        admin = self.register("admin")
        invite_response = self.client.post(
            "/api/v1/auth/invites",
            json={"max_uses": 1, "expires_days": 14},
            headers=self.auth_headers(admin),
        )
        self.assertEqual(invite_response.status_code, 201, invite_response.text)
        member = self.register("member", invite_response.json()["code"])
        return admin, member

    def test_auth_required_first_user_admin_and_invite_registration(self) -> None:
        self.assertEqual(self.client.get("/api/v1/books/").status_code, 401)

        admin, member = self.create_invited_user()
        self.assertTrue(admin["user"]["is_admin"])
        self.assertFalse(member["user"]["is_admin"])

        reused_invite = self.client.post(
            "/api/v1/auth/register",
            json={
                "username": "third-user",
                "password": "password-123",
                "invite_code": "invalid-code",
            },
        )
        self.assertEqual(reused_invite.status_code, 400)

    def test_books_chapters_conversations_settings_and_knowledge_are_isolated(self) -> None:
        admin, member = self.create_invited_user()
        admin_headers = self.auth_headers(admin)
        member_headers = self.auth_headers(member)

        book_response = self.client.post(
            "/api/v1/books/",
            json={"title": "Admin book"},
            headers=admin_headers,
        )
        self.assertEqual(book_response.status_code, 201, book_response.text)
        book_id = book_response.json()["id"]

        chapter_response = self.client.post(
            f"/api/v1/books/{book_id}/chapters",
            json={"title": "Chapter one", "content": "private text", "order": 1},
            headers=admin_headers,
        )
        self.assertEqual(chapter_response.status_code, 201, chapter_response.text)
        chapter_id = chapter_response.json()["id"]

        conversation_response = self.client.post(
            "/api/v1/conversations/",
            json={"title": "Private conversation", "messages": [{"role": "user", "content": "secret"}]},
            headers=admin_headers,
        )
        self.assertEqual(conversation_response.status_code, 201, conversation_response.text)
        conversation_id = conversation_response.json()["id"]

        admin_settings = self.client.patch(
            "/api/v1/settings/",
            json={"font_size": 22},
            headers=admin_headers,
        )
        self.assertEqual(admin_settings.status_code, 200, admin_settings.text)

        with Session(self.engine) as session:
            document = KnowledgeDocument(user_id="admin", project_id=str(book_id), title="Private notes")
            session.add(document)
            session.commit()
            session.refresh(document)
            session.add(
                KnowledgeChunk(
                    document_id=document.id,
                    user_id="admin",
                    project_id=str(book_id),
                    text="private knowledge",
                )
            )
            session.commit()
            document_id = document.id

        self.assertEqual(self.client.get(f"/api/v1/books/{book_id}", headers=member_headers).status_code, 404)
        self.assertEqual(
            self.client.get(f"/api/v1/books/{book_id}/chapters/{chapter_id}", headers=member_headers).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/api/v1/conversations/{conversation_id}", headers=member_headers).status_code,
            404,
        )
        self.assertEqual(self.client.get("/api/v1/books/", headers=member_headers).json(), [])
        self.assertEqual(self.client.get("/api/v1/conversations/?include_empty=true", headers=member_headers).json(), [])

        member_settings = self.client.get("/api/v1/settings/", headers=member_headers)
        self.assertEqual(member_settings.status_code, 200, member_settings.text)
        self.assertEqual(member_settings.json()["font_size"], 16)

        member_documents = self.client.get(
            f"/api/v1/knowledge/documents?user_id=admin&project_id={book_id}",
            headers=member_headers,
        )
        self.assertEqual(member_documents.status_code, 200, member_documents.text)
        self.assertEqual(member_documents.json()["items"], [])
        self.assertEqual(
            self.client.delete(f"/api/v1/knowledge/documents/{document_id}", headers=member_headers).status_code,
            404,
        )

    def test_ai_health_reports_missing_key_without_calling_provider(self) -> None:
        admin = self.register("admin")
        response = self.client.get("/api/v1/ai/health", headers=self.auth_headers(admin))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["configured"])

    def test_ai_provider_configs_migrate_legacy_key_and_stay_private(self) -> None:
        admin, member = self.create_invited_user()
        admin_headers = self.auth_headers(admin)
        member_headers = self.auth_headers(member)

        legacy = self.client.patch(
            "/api/v1/settings/",
            json={"ai_provider": "deepseek", "deepseek_api_key": "legacy-secret-1234"},
            headers=admin_headers,
        )
        self.assertEqual(legacy.status_code, 200, legacy.text)

        migrated = self.client.get("/api/v1/ai/providers/", headers=admin_headers)
        self.assertEqual(migrated.status_code, 200, migrated.text)
        self.assertEqual(len(migrated.json()["items"]), 1)
        migrated_config = migrated.json()["items"][0]
        self.assertTrue(migrated_config["is_active"])
        self.assertTrue(migrated_config["has_api_key"])
        self.assertEqual(migrated_config["api_key_hint"], "1234")
        self.assertNotIn("api_key", migrated_config)
        self.assertNotIn("api_key_enc", migrated_config)

        created = self.client.post(
            "/api/v1/ai/providers/",
            json={
                "name": "Local model",
                "provider": "openai_compatible",
                "base_url": "http://127.0.0.1:11434/v1/",
                "model": "novel-model",
                "api_key": "local-key-5678",
                "activate": True,
            },
            headers=admin_headers,
        )
        self.assertEqual(created.status_code, 201, created.text)
        created_config = created.json()
        self.assertEqual(created_config["base_url"], "http://127.0.0.1:11434/v1")
        self.assertTrue(created_config["is_active"])

        health = self.client.get("/api/v1/ai/health", headers=admin_headers)
        self.assertEqual(health.status_code, 200, health.text)
        self.assertTrue(health.json()["configured"])
        self.assertEqual(health.json()["profile_id"], created_config["id"])
        self.assertEqual(health.json()["model"], "novel-model")

        member_list = self.client.get("/api/v1/ai/providers/", headers=member_headers)
        self.assertEqual(member_list.status_code, 200, member_list.text)
        self.assertNotIn(created_config["id"], [item["id"] for item in member_list.json()["items"]])
        self.assertEqual(
            self.client.delete(
                f"/api/v1/ai/providers/{created_config['id']}",
                headers=member_headers,
            ).status_code,
            404,
        )

    def test_ai_provider_connection_test_and_models_endpoint(self) -> None:
        admin = self.register("admin")
        headers = self.auth_headers(admin)
        self.client.get("/api/v1/settings/", headers=headers)
        created = self.client.post(
            "/api/v1/ai/providers/",
            json={
                "name": "Test API",
                "provider": "openai_compatible",
                "base_url": "https://models.example.test/v1",
                "model": "writer-pro",
                "api_key": "test-key-4321",
                "activate": True,
            },
            headers=headers,
        ).json()

        with patch(
            "app.api.v1.endpoints.ai_providers.discover_provider_models",
            return_value=["writer-lite", "writer-pro"],
        ) as discover_models:
            models = self.client.get(
                f"/api/v1/ai/providers/{created['id']}/models",
                headers=headers,
            )
            draft_models = self.client.post(
                "/api/v1/ai/providers/discover-models",
                json={
                    "config_id": created["id"],
                    "base_url": "https://draft.example.test/v1/",
                },
                headers=headers,
            )
            unsaved_models = self.client.post(
                "/api/v1/ai/providers/discover-models",
                json={
                    "base_url": "https://new.example.test/v1",
                    "api_key": "new-key-1234",
                },
                headers=headers,
            )
            tested = self.client.post(
                f"/api/v1/ai/providers/{created['id']}/test",
                headers=headers,
            )

        self.assertEqual(models.status_code, 200, models.text)
        self.assertEqual(models.json()["items"], ["writer-lite", "writer-pro"])
        self.assertEqual(draft_models.status_code, 200, draft_models.text)
        self.assertEqual(draft_models.json()["items"], ["writer-lite", "writer-pro"])
        self.assertEqual(draft_models.json()["selected_model"], "writer-pro")
        self.assertEqual(unsaved_models.status_code, 200, unsaved_models.text)
        self.assertEqual(unsaved_models.json()["selected_model"], "")
        discover_models.assert_any_call(
            api_key="test-key-4321",
            base_url="https://draft.example.test/v1",
        )
        discover_models.assert_any_call(
            api_key="new-key-1234",
            base_url="https://new.example.test/v1",
        )
        self.assertEqual(tested.status_code, 200, tested.text)
        self.assertTrue(tested.json()["ok"])

        refreshed = self.client.get("/api/v1/ai/providers/", headers=headers).json()
        tested_config = next(item for item in refreshed["items"] if item["id"] == created["id"])
        self.assertEqual(tested_config["last_test_status"], "success")

    def test_ai_runtime_uses_active_provider_profile(self) -> None:
        from app.services.ai_provider import AIProviderFactory, get_ai_provider

        admin = self.register("admin")
        headers = self.auth_headers(admin)
        self.client.get("/api/v1/settings/", headers=headers)
        created = self.client.post(
            "/api/v1/ai/providers/",
            json={
                "name": "Runtime profile",
                "provider": "openai_compatible",
                "base_url": "https://runtime.example.test/v1",
                "model": "novel-runtime-model",
                "api_key": "runtime-key-9876",
                "activate": True,
            },
            headers=headers,
        )
        self.assertEqual(created.status_code, 201, created.text)

        sentinel = object()
        with Session(self.engine) as session, patch.object(
            AIProviderFactory,
            "get_provider",
            return_value=sentinel,
        ) as factory:
            provider = get_ai_provider(session=session, user_id="admin")

        self.assertIs(provider, sentinel)
        factory.assert_called_once_with(
            "openai_compatible",
            api_key="runtime-key-9876",
            base_url="https://runtime.example.test/v1",
            model="novel-runtime-model",
        )

    def test_ai_health_does_not_use_a_different_provider_environment_key(self) -> None:
        old_key = settings.DEEPSEEK_API_KEY
        settings.DEEPSEEK_API_KEY = "server-deepseek-key"
        try:
            admin = self.register("admin")
            headers = self.auth_headers(admin)
            updated = self.client.patch(
                "/api/v1/settings/",
                json={"ai_provider": "openai"},
                headers=headers,
            )
            self.assertEqual(updated.status_code, 200, updated.text)
            response = self.client.get("/api/v1/ai/health", headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["provider"], "openai")
            self.assertFalse(response.json()["configured"])
        finally:
            settings.DEEPSEEK_API_KEY = old_key

    def test_chapter_revision_history_can_restore_and_stays_private(self) -> None:
        admin, member = self.create_invited_user()
        admin_headers = self.auth_headers(admin)
        member_headers = self.auth_headers(member)
        book = self.client.post("/api/v1/books/", json={"title": "Revision book"}, headers=admin_headers).json()
        chapter = self.client.post(
            f"/api/v1/books/{book['id']}/chapters",
            json={"title": "Chapter", "content": "version one", "order": 1},
            headers=admin_headers,
        ).json()

        updated = self.client.patch(
            f"/api/v1/books/{book['id']}/chapters/{chapter['id']}",
            json={"content": "version two"},
            headers=admin_headers,
        )
        self.assertEqual(updated.status_code, 200, updated.text)

        history = self.client.get(
            f"/api/v1/books/{book['id']}/chapters/{chapter['id']}/revisions",
            headers=admin_headers,
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json()[0]["content"], "version one")
        revision_id = history.json()[0]["id"]

        self.assertEqual(
            self.client.get(
                f"/api/v1/books/{book['id']}/chapters/{chapter['id']}/revisions",
                headers=member_headers,
            ).status_code,
            404,
        )

        restored = self.client.post(
            f"/api/v1/books/{book['id']}/chapters/{chapter['id']}/revisions/{revision_id}/restore",
            headers=admin_headers,
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["content"], "version one")

    def test_admin_can_manage_login_cover_and_user_access(self) -> None:
        admin, member = self.create_invited_user()
        admin_headers = self.auth_headers(admin)
        member_headers = self.auth_headers(member)

        member_upload = self.client.post(
            "/api/v1/admin/login-cover",
            files={"file": ("cover.jpg", b"member-cover", "image/jpeg")},
            headers=member_headers,
        )
        self.assertEqual(member_upload.status_code, 403)

        upload = self.client.post(
            "/api/v1/admin/login-cover",
            files={"file": ("cover.jpg", b"admin-cover", "image/jpeg")},
            headers=admin_headers,
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        cover = self.client.get("/api/v1/admin/login-cover")
        self.assertEqual(cover.status_code, 200, cover.text)
        self.assertEqual(cover.content, b"admin-cover")

        member_cannot_manage = self.client.patch(
            "/api/v1/admin/users/admin",
            json={"is_active": False},
            headers=member_headers,
        )
        self.assertEqual(member_cannot_manage.status_code, 403)

        self_cannot_disable = self.client.patch(
            "/api/v1/admin/users/admin",
            json={"is_active": False},
            headers=admin_headers,
        )
        self.assertEqual(self_cannot_disable.status_code, 400)

        disabled = self.client.patch(
            "/api/v1/admin/users/member",
            json={"is_active": False},
            headers=admin_headers,
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertFalse(disabled.json()["is_active"])
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login",
                json={"username": "member", "password": "password-123"},
            ).status_code,
            401,
        )

        restored = self.client.patch(
            "/api/v1/admin/users/member",
            json={"is_active": True, "is_admin": True},
            headers=admin_headers,
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertTrue(restored.json()["is_active"])
        self.assertTrue(restored.json()["is_admin"])

        clear = self.client.delete("/api/v1/admin/login-cover", headers=admin_headers)
        self.assertEqual(clear.status_code, 204, clear.text)
        self.assertEqual(self.client.get("/api/v1/admin/login-cover").status_code, 404)

    def test_conversations_can_be_scoped_to_a_book(self) -> None:
        admin, _ = self.create_invited_user()
        headers = self.auth_headers(admin)

        book_one = self.client.post("/api/v1/books/", json={"title": "Book one"}, headers=headers)
        book_two = self.client.post("/api/v1/books/", json={"title": "Book two"}, headers=headers)
        self.assertEqual(book_one.status_code, 201, book_one.text)
        self.assertEqual(book_two.status_code, 201, book_two.text)

        conv_one = self.client.post(
            "/api/v1/conversations/",
            json={"title": "Book one chat", "book_id": book_one.json()["id"]},
            headers=headers,
        )
        conv_two = self.client.post(
            "/api/v1/conversations/",
            json={"title": "Book two chat", "book_id": book_two.json()["id"]},
            headers=headers,
        )
        self.assertEqual(conv_one.status_code, 201, conv_one.text)
        self.assertEqual(conv_two.status_code, 201, conv_two.text)
        self.assertEqual(conv_one.json()["book_id"], book_one.json()["id"])
        self.assertEqual(conv_two.json()["book_id"], book_two.json()["id"])

        filtered = self.client.get(
            f"/api/v1/conversations/?book_id={book_one.json()['id']}",
            headers=headers,
        )
        self.assertEqual(filtered.status_code, 200, filtered.text)
        titles = [conv["title"] for conv in filtered.json()]
        self.assertIn("Book one chat", titles)
        self.assertNotIn("Book two chat", titles)

        archived = self.client.patch(
            f"/api/v1/conversations/{conv_one.json()['id']}",
            json={"archived": True},
            headers=headers,
        )
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertTrue(archived.json()["archived"])
        hidden = self.client.get(
            f"/api/v1/conversations/?book_id={book_one.json()['id']}",
            headers=headers,
        )
        self.assertNotIn("Book one chat", [conv["title"] for conv in hidden.json()])


if __name__ == "__main__":
    unittest.main()
