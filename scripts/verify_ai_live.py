"""Explicitly authorized live regression using only the synthetic Wugang book."""
import json
import argparse
import os
import re
import sys
from pathlib import Path

import requests
from websockets.sync.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.ai_context import parse_structured_output


def evaluate_long_run(results):
    """Content checks are separate from transport/format success."""
    if len(results) != 20:
        return {}
    def copy_at(turn):
        match = re.search(r"<NOVELCAT_COPY>\s*([\s\S]*?)\s*</NOVELCAT_COPY>", results[turn - 1]["raw"])
        return match[1] if match else ""
    fifth, sixth = copy_at(11), copy_at(13)
    # The fixture uses Chinese full stops for its first two prose sentences.
    old_parts, new_parts = fifth.split("。", 2), sixth.split("。", 2)
    return {
        "unchanged_after_first_two_sentences": bool(fifth and sixth and len(old_parts) == 3 and len(new_parts) == 3
                                                   and old_parts[2].strip() == new_parts[2].strip()),
        "eighth_version_repeated_exactly": bool(copy_at(17)) and copy_at(17) == copy_at(19),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--long", action="store_true")
    parser.add_argument("--max-tokens", type=int)
    args = parser.parse_args()
    api = "http://127.0.0.1:8000/api/v1"
    login = requests.post(api + "/auth/login", json={
        "username": "shysta", "password": os.environ["NOVELCAT_TEST_PASSWORD"],
    }, timeout=15)
    login.raise_for_status()
    token = login.json()["access_token"]
    headers = {"Authorization": "Bearer " + token}
    book = requests.get(api + "/books/", headers=headers, timeout=15)
    book.raise_for_status()
    assert any(b["id"] == 4 and b["title"] == "AI长篇压力测试·雾港" for b in book.json())
    health = requests.get(api + "/ai/health", headers=headers, timeout=15).json()
    print(json.dumps({"model": health.get("model"), "provider": health.get("provider"), "base_url": health.get("base_url")}, ensure_ascii=True), flush=True)
    chapters = requests.get(api + "/books/4/chapters", headers=headers, timeout=15).json()
    history = []
    prompts = [
        "这是新对话。按作品文档林雾惯用哪只手？钥匙是什么材质？你能知道其他聊天里讨论的改动吗？请简短回答。",
        "仅在本聊天试写：林雾改为左撇子，作品文档不改。接着第3章续写约350字，林雾用惯用手扶住沈砚舟走上防波堤。距白潮仍约三个小时十二分，保持限知视角和克制暧昧，复制区只要正文。",
        "把上一段润色得更有紧张感，仍约350字，保留惯用手、铜钥匙和时间，不要加入新设定，复制区给完整可用正文。",
        "检查刚才的建议：沈砚舟直接游过1.8公里，用智能手机定位，顾巡亲自持枪威胁。这三项是否符合本书设定？只检查不要续写，也不要把这些建议记成作者决定。",
        "这是另一个全新聊天。请仅按作品文档告诉我林雾惯用哪只手，钥匙是什么材质。简短回答。",
    ]
    if args.long:
        prompts[4:4] = [
            "回到刚才润色后的正文，把它叫做第二版。只调整最后一句，停在铜钥匙碰到掌心的瞬间。给出完整正文，不新增事件。",
            "只讨论：第二版中谁在扶谁？林雾用哪只手？不要生成新版本。",
            "设想把铜钥匙换成银钥匙会怎样？仅讨论，不采用，不改设定，不输出正文。",
            "继续润色第二版，仍保留铜钥匙和左撇子。减少比喻，保持限知视角，约300字。此为第三版。",
            "第三版只加强环境声音，不新增人物，不改事件先后。给完整正文，约300字。称第四版。",
            "检查第四版有没有擅自改变距白潮的时间，只讨论，不推进时间。",
            "把第四版改得更克制，人物不要直接说出感情。事件和时间不变，约300字。称第五版。",
            "我不采用之前银钥匙的想法。确认当前讨论中钥匙材质和林雾惯用手，只要简短答案。",
            "第五版只改开头两句，别动后面的句子，给出完整正文，称第六版。",
            "对比第二版与第六版，指出具体改了什么。如果看不到完整旧版，请直说，不要编造原句。只讨论。",
            "第六版里加入一句沈砚舟的短对话，不超过十个字，不解释情绪。给完整正文，称第七版。",
            "检查第七版有没有视角越界。只指出问题，不改正文，不把猜测记成设定。",
            "修正第七版可能的视角越界，其他内容尽量不动，给完整正文，称第八版。",
            "最终核对：当前聊天试写的惯用手、作品文档原本的惯用手、钥匙材质、距白潮时间分别是什么？不要混淆讨论与文档。",
            "只给第八版的完整可用正文，不要在复制区加标题、版本号或说明，不新增情节。",
        ]
    results = []
    for index, prompt in enumerate(prompts, 1):
        if index == len(prompts):
            history = []
        history.append({"role": "user", "content": prompt})
        payload = {"messages": history, "project_id": "4", "book_id": 4,
                   "conversation_id": 28, "current_chapter_id": 14,
                   "use_memory": False}
        if args.max_tokens:
            payload["max_length"] = args.max_tokens
        chunks = []
        diagnostics = None
        error = None
        with connect("ws://127.0.0.1:8000/api/v1/ai/ws?auth_token=" + token, open_timeout=15) as ws:
            ws.send(json.dumps(payload, ensure_ascii=False))
            while True:
                event = json.loads(ws.recv(timeout=90))
                if event.get("type") == "token":
                    chunks.append(event.get("text", ""))
                elif event.get("type") == "generation_metadata":
                    diagnostics = event.get("data")
                elif event.get("type") == "error":
                    error = event.get("message", "AI error")
                    break
                elif event.get("type") == "done":
                    break
        raw = "".join(chunks)
        reply, copy = parse_structured_output(raw)
        # Match the UI: only complete blocks qualify as a copyable draft.
        reply_match = re.search(r"<NOVELCAT_REPLY>\s*([\s\S]*?)\s*</NOVELCAT_REPLY>", raw)
        copy_match = re.search(r"<NOVELCAT_COPY>\s*([\s\S]*?)\s*</NOVELCAT_COPY>", raw)
        structured = bool(reply_match and copy_match)
        result = {"turn": index, "prompt": prompt, "raw": raw,
                  "copy_chars": len(copy_match[1]) if structured and not error else 0,
                  "structured": structured, "diagnostics": diagnostics, "error": error,
                  "internal_leak": any(t in raw for t in ["此前给出的可复制内容", "NOVELCAT_PREVIOUS_COPY"]),
                  "empty": not (reply or copy)}
        results.append(result)
        print(json.dumps({key: value for key, value in result.items() if key not in ("raw", "prompt")}, ensure_ascii=True), flush=True)
        if error:
            continue
        if structured:
            history.append({"role": "assistant", "content": f"<NOVELCAT_REPLY>\n{reply}\n</NOVELCAT_REPLY>\n<NOVELCAT_COPY>\n{copy}\n</NOVELCAT_COPY>"})
        elif raw.strip():
            history.append({"role": "assistant", "content": re.sub(r"</?NOVELCAT_(?:REPLY|COPY)>", "", raw)})
    after = requests.get(api + "/books/4/chapters", headers=headers, timeout=15).json()
    print(json.dumps({"chapters_unchanged": chapters == after}), flush=True)
    report = Path(__file__).resolve().parents[1] / ".run" / "ai-live-report.json"
    report.parent.mkdir(exist_ok=True)
    semantic_checks = evaluate_long_run(results)
    print(json.dumps({"semantic_checks": semantic_checks}), flush=True)
    report.write_text(json.dumps({"results": results, "chapters_unchanged": chapters == after,
                                  "semantic_checks": semantic_checks}, ensure_ascii=False, indent=2), encoding="utf-8")
    if (chapters != after or not all(semantic_checks.values())
            or any(r["error"] or r["empty"] or not r["structured"] or r["internal_leak"] for r in results)):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
