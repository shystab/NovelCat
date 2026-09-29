import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from sqlmodel import create_engine

from app.main import app


class ScopedRevisionWebSocketTests(unittest.TestCase):
    def request(self, output):
        service = Mock()
        service.provider.last_stream_diagnostics = None
        service.stream_chat.return_value = iter([
            {"type": "agent_step", "step": {"id": "generating-answer", "status": "running"}},
            output[:20], output[20:],
            {"type": "agent_step", "step": {"id": "generating-answer", "status": "completed"}},
        ])
        engine = create_engine("sqlite://")
        # Do not enter the app lifespan, which migrates the real workspace DB.
        client = TestClient(app)
        module = "app.api.v1.endpoints.ai."
        try:
            with patch(module + "engine", engine), \
                 patch(module + "verify_websocket_access", AsyncMock(return_value=True)), \
                 patch(module + "get_websocket_user", return_value=SimpleNamespace(username="test")), \
                 patch(module + "check_api_key", return_value=True), \
                 patch(module + "get_ai_service", return_value=service):
                with client.websocket_connect("/api/v1/ai/ws") as ws:
                    ws.send_json({"messages": [{"role": "user", "content": "只改开头"}],
                                  "draft_reference": {"label": "回复稿 1", "text": "甲。乙。丙不能删。", "scope": "opening_two"}})
                    events = []
                    while True:
                        event = ws.receive_json()
                        events.append(event)
                        if event["type"] in ("done", "error"):
                            break
            return events, service
        finally:
            client.close()
            engine.dispose()

    def test_only_validated_merged_draft_is_emitted(self):
        events, service = self.request("<NOVELCAT_REPLY>说明</NOVELCAT_REPLY><NOVELCAT_COPY>新甲。新乙。</NOVELCAT_COPY>")
        tokens = [e["text"] for e in events if e["type"] == "token"]
        self.assertEqual(len(tokens), 1)
        self.assertIn("新甲。新乙。丙不能删。", tokens[0])
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(service.stream_chat.call_args.kwargs["draft_reference"]["text"], "甲。乙。丙不能删。")

    def test_out_of_scope_output_never_emits_copy_or_success(self):
        events, _ = self.request("<NOVELCAT_REPLY>说明</NOVELCAT_REPLY><NOVELCAT_COPY>新甲。新乙。乱改丙。</NOVELCAT_COPY>")
        self.assertEqual(events[-1]["type"], "error")
        self.assertFalse(any(e["type"] == "token" or e.get("step", {}).get("status") == "completed" for e in events))
