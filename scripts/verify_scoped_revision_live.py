"""Opt-in live checks against the authorized synthetic book, without chapter writes."""
import json
import os
import re

import requests
from websockets.sync.client import connect


def main():
    api = "http://127.0.0.1:8000/api/v1"
    login = requests.post(api + "/auth/login", json={
        "username": "shysta", "password": os.environ["NOVELCAT_TEST_PASSWORD"],
    }, timeout=15)
    login.raise_for_status()
    token = login.json()["access_token"]
    headers = {"Authorization": "Bearer " + token}

    def get(path):
        response = requests.get(api + path, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()

    assert any(b["id"] == 4 and b["title"] == "AI长篇压力测试·雾港" for b in get("/books/"))
    before = get("/books/4/chapters")
    source = "她接过外套，没有道谢。铁门旁是一条维修小道。沈砚舟走在前面，左手扶墙，右耳朝向她。\n\n旧表贴着腿，指针停在03:17。离白潮还有三个小时十二分。"
    history = []
    results = []
    for scope in ("opening_two", "last_paragraph"):
        prompt = "把选中的范围润色得更克制，保留事件与时间，不新增设定。"
        history.append({"role": "user", "content": prompt})
        request = {
            "messages": history, "project_id": "4", "book_id": 4,
            "current_chapter_id": 14, "use_memory": False, "max_length": 1800,
            "draft_reference": {"label": "合成测试原稿", "text": source, "scope": scope},
        }
        chunks, error, diagnostics = [], None, None
        with connect("ws://127.0.0.1:8000/api/v1/ai/ws?auth_token=" + token, open_timeout=15) as ws:
            ws.send(json.dumps(request, ensure_ascii=False))
            while True:
                event = json.loads(ws.recv(timeout=90))
                if event.get("type") == "token":
                    chunks.append(event["text"])
                elif event.get("type") == "generation_metadata":
                    diagnostics = event["data"]
                elif event.get("type") == "error":
                    error = event.get("message")
                    break
                elif event.get("type") == "done":
                    break
        raw = "".join(chunks)
        match = re.search(r"<NOVELCAT_COPY>\n([\s\S]*?)\n</NOVELCAT_COPY>", raw)
        draft = match[1] if match else ""
        if scope == "opening_two":
            original_tail = source.split("。", 2)[2]
            new_parts = draft.split("。", 2)
            unchanged = len(new_parts) == 3 and new_parts[2] == original_tail
        else:
            unchanged = draft.rsplit("\n\n", 1)[0] == source.rsplit("\n\n", 1)[0]
        result = {"scope": scope, "error": error, "unchanged_outside_scope": unchanged,
                  "copy_chars": len(draft), "diagnostics": diagnostics}
        print(json.dumps(result, ensure_ascii=True), flush=True)
        results.append(result)
        if not error:
            history.append({"role": "assistant", "content": raw})
    unchanged_chapters = before == get("/books/4/chapters")
    print(json.dumps({"chapters_unchanged": unchanged_chapters}), flush=True)
    return 0 if unchanged_chapters and all(not r["error"] and r["unchanged_outside_scope"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
