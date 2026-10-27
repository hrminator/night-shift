"""Day 1 step 2 part 3: prove Spark reads the fixture sources.

Uploads both Baltic PDFs once each via the files endpoint (purpose
``user_data``; ``expires_after`` was tried and is ignored by the API, so no
expiry is available) and sends them by file id, plus the portal JSON inline.
Asks muse-spark-1.3, with a ``record_claim`` tool, to record the delivery
commitment each document states, quoted verbatim with the source name.

Then replays the first call's output items (encrypted reasoning intact) with
the tool results, and compares input token counts to see whether the PDFs are
billed again on a replayed turn.

Key: NIGHT_SHIFT_API_KEY_EVAL, never printed. Bodies are logged by
app.adapter (minus the key).

Run: uv run python scripts/read_sources.py
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, ".")

from app.adapter import BASE_URL, MODEL, api_key, reasoning_items_of, respond

SCAN_PDF = Path("fixtures/baltic_quote_Q-1187-B.pdf")
TEXT_PDF = Path("fixtures/baltic_quote_Q-1187-B_text.pdf")
PORTAL_JSON = Path("fixtures/vestland_portal.json")

RECORD_CLAIM_TOOL = {
    "type": "function",
    "name": "record_claim",
    "description": (
        "Record the delivery commitment one source document states. "
        "Call once per document."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Document name, e.g. baltic_quote_Q-1187-B.pdf",
            },
            "version": {
                "type": "string",
                "description": "Document version if the source states one",
            },
            "delivery_commitment": {
                "type": "string",
                "description": (
                    "What the document commits to about delivery, "
                    "quoted verbatim from the document"
                ),
            },
        },
        "required": ["source", "delivery_commitment"],
        "additionalProperties": False,
    },
}

INSTRUCTIONS = (
    "You are Night Shift's source reader. Read each attached document and "
    "call record_claim once per document with the delivery commitment it "
    "states, quoted verbatim, with the source name. Three documents: "
    "baltic_quote_Q-1187-B.pdf (scan-styled image-only PDF), "
    "baltic_quote_Q-1187-B_text.pdf (same content as text), and the "
    "Vestland portal record (JSON). Quote exactly what each says about "
    "delivery; do not paraphrase the commitment itself."
)


def upload_pdf(path: Path) -> dict:
    headers = {"Authorization": f"Bearer {api_key()}"}
    with path.open("rb") as handle:
        files = {"file": (path.name, handle, "application/pdf")}
        response = httpx.post(
            BASE_URL + "/files",
            headers=headers,
            files=files,
            data={"purpose": "user_data"},
            timeout=60.0,
        )
    response.raise_for_status()
    return response.json()


def delete_file(file_id: str) -> None:
    headers = {"Authorization": f"Bearer {api_key()}"}
    url = BASE_URL + "/files/" + file_id
    httpx.delete(url, headers=headers, timeout=30.0)


def function_calls_of(output_items: list) -> list:
    return [i for i in output_items if i.get("type") == "function_call"]


def usage_line(result: dict) -> dict:
    usage = result.get("usage") or {}
    return {
        "seconds": round(result["seconds"], 2),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": (
            usage.get("reasoning_tokens")
            or (usage.get("output_tokens_details") or {}).get("reasoning_tokens")
        ),
        "model": result.get("model"),
        "status": result.get("status"),
        "incomplete_details": result.get("incomplete_details"),
    }


def main() -> int:
    base = BASE_URL
    print(f"files base: {base}/files (purpose=user_data; no expiry supported)")
    scan_meta = upload_pdf(SCAN_PDF)
    text_meta = upload_pdf(TEXT_PDF)
    print(f"uploaded {SCAN_PDF.name} -> {scan_meta['id']} ({scan_meta['bytes']} bytes)")
    print(f"uploaded {TEXT_PDF.name} -> {text_meta['id']} ({text_meta['bytes']} bytes)")

    portal_record = json.loads(PORTAL_JSON.read_text(encoding="utf-8"))
    user_content = [
        {"type": "input_file", "file_id": scan_meta["id"]},
        {"type": "input_file", "file_id": text_meta["id"]},
        {
            "type": "input_text",
            "text": "Vestland portal record (vestland_portal.json, version 1):\n"
            + json.dumps(portal_record, ensure_ascii=False),
        },
        {
            "type": "input_text",
            "text": "Record a claim for each of the three documents.",
        },
    ]
    first_input = [{"type": "message", "role": "user", "content": user_content}]

    try:
        call1 = respond(
            INSTRUCTIONS, first_input, tools=[RECORD_CLAIM_TOOL],
            effort="low", max_output_tokens=2048,
        )
        file_send_mode = "file_id"
    except Exception as exc:  # noqa: BLE001 — probe fallback path
        print(f"file_id send failed ({exc}); retrying with base64-inline PDFs")
        for part, path in ((user_content[0], SCAN_PDF), (user_content[1], TEXT_PDF)):
            blob = base64.b64encode(path.read_bytes()).decode("ascii")
            part.clear()
            part.update(
                {
                    "type": "input_file",
                    "filename": path.name,
                    "file_data": f"data:application/pdf;base64,{blob}",
                }
            )
        call1 = respond(
            INSTRUCTIONS, first_input, tools=[RECORD_CLAIM_TOOL],
            effort="low", max_output_tokens=2048,
        )
        file_send_mode = "base64-inline"
    print(f"send mode: {file_send_mode}")
    print("call1 usage: " + json.dumps(usage_line(call1)))

    claims = []
    for item in function_calls_of(call1["output"]):
        args = json.loads(item.get("arguments") or "{}")
        claims.append({"call_id": item.get("call_id"), **args})
    print(f"claims recorded: {len(claims)}")
    for claim in claims:
        print(json.dumps(claim, ensure_ascii=False))
    print(f"reasoning items in call1: {len(reasoning_items_of(call1['output']))}")

    # Turn 2: replay call-1 output items (encrypted reasoning intact) plus
    # one function_call_output per call, and ask for nothing new.
    replay_input = list(call1["output"]) + [
        {
            "type": "function_call_output",
            "call_id": claim["call_id"],
            "output": json.dumps({"stored": True, "source": claim.get("source")}),
        }
        for claim in claims
        if claim.get("call_id")
    ]
    replay_input.append(
        {
            "type": "message",
            "role": "user",
            "content": "Claims stored. Reply with exactly: claims stored.",
        }
    )
    call2 = respond(
        INSTRUCTIONS, replay_input, tools=[RECORD_CLAIM_TOOL],
        effort="low", max_output_tokens=2048,
    )
    print("call2 usage: " + json.dumps(usage_line(call2)))
    print(f"call2 text: {call2['text'][:200]!r}")

    in1 = (call1.get("usage") or {}).get("input_tokens")
    in2 = (call2.get("usage") or {}).get("input_tokens")
    print(f"replay billing: call1 input {in1} vs call2 input {in2}")

    delete_file(scan_meta["id"])
    delete_file(text_meta["id"])
    print("uploaded files deleted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
