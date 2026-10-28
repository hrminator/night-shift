"""Night B ("change one fact"): a fresh night on the one-line venue override.

Night A (the hero): the venue letter covers the Thursday event only, so at
00:38 the agent cannot verify that the venue can receive the van, and it
wakes the owner. Night B: the same night with one fixture line changed (the
venue accepts Wednesday deliveries), run fresh from 21:30 on a new job id,
with the same policy and model configuration, under the supervision arm. A
visitor can run it live from the front door and compare it with Night A.

The override is the venue override of the matching eval case
(necessity_no_wake): the contrast venue text gains exactly one line in
exactly one fixture (venue_confirmation.md). The brief — and with it the
standing permission — is byte-identical.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

#: The eval case whose venue override defines Night B.
NIGHT_B_CASE_ID = "necessity_no_wake"

#: The one fixture the override touches.
NIGHT_B_CHANGED_FILE = "venue_confirmation.md"

#: Env var pinning the results folder the comparison line reads.
NIGHT_B_RESULTS_ENV_VAR = "NIGHT_B_RESULTS_DIR"

#: Source documents hashed as the fixture set (the brief is instruction
#: text, so it belongs to the policy hash, not the fixture hash).
SOURCE_FIXTURES = (
    "nordtrykk.html",
    "vestland_portal.json",
    "baltic_shipping_terms.html",
    "venue_confirmation.md",
    "addresses.json",
    "studio.json",
    "decision_facts.json",
)

#: Job statuses at which the progress page stops polling.
TERMINAL_STATUSES = ("done", "decision_done", "waiting_for_owner", "failed")


def night_b_case() -> dict:
    """The eval case file that defines Night B's override."""
    from app import eval_world
    return eval_world.load_case(NIGHT_B_CASE_ID)


def venue_variant() -> str:
    """Night B's venue variant, read from the case file."""
    case = night_b_case()
    return str((case.get("overrides") or {}).get("venue", "hero"))


def hero_venue_text() -> str:
    from app import runner as _runner
    return _runner.venue_text("hero")


def contrast_venue_text() -> str:
    from app import runner as _runner
    return _runner.venue_text("contrast")


def changed_lines() -> list[str]:
    """Non-empty lines the contrast venue text adds over the hero text."""
    hero = hero_venue_text().splitlines()
    return [line for line in contrast_venue_text().splitlines()
            if line.strip() and line not in hero]


def night_b_sentence() -> str:
    """The changed sentence for Night B, read from the fixtures."""
    return " ".join(changed_lines())


def night_a_sentence() -> str:
    """The venue letter's delivery sentence as it is in Night A."""
    for paragraph in hero_venue_text().split("\n\n"):
        if "says nothing" in paragraph:
            return " ".join(paragraph.split())
    return ""


def fixture_texts(variant: str) -> dict[str, str]:
    """Source fixture texts as one night variant loads them."""
    from app import runner as _runner
    texts = {}
    for name in SOURCE_FIXTURES:
        if name == NIGHT_B_CHANGED_FILE:
            texts[name] = _runner.venue_text(variant)
        else:
            texts[name] = _runner.fixture_text(name)
    return texts


def fixture_diff() -> dict[str, dict[str, list[str]]]:
    """Per-file added/removed lines, contrast vs hero, sources plus brief.

    Only files that differ appear. The brief is included to prove the
    standing permission is byte-identical on both nights.
    """
    from app import runner as _runner
    names = list(SOURCE_FIXTURES) + ["brief.md"]
    hero = fixture_texts("hero")
    hero["brief.md"] = _runner.fixture_text("brief.md")
    contrast = fixture_texts("contrast")
    contrast["brief.md"] = _runner.fixture_text("brief.md")
    diff: dict[str, dict[str, list[str]]] = {}
    for name in names:
        old = hero[name].splitlines()
        new = contrast[name].splitlines()
        added = [line for line in new if line not in old]
        removed = [line for line in old if line not in new]
        if added or removed:
            diff[name] = {"added": added, "removed": removed}
    return diff


def policy_text(arm: str = "supervision") -> str:
    """The instruction text the app sends, one stable string per arm.

    The venue fixture travels in the input messages, never here, so Night
    A and Night B share this text exactly.
    """
    from app import runner as _runner
    return "\n\n".join([
        _runner.build_read_instructions(),
        _runner.build_reassess_instructions(arm),
        _runner.build_resume_instructions("policy", {}, arm),
    ])


def policy_hash(arm: str = "supervision") -> str:
    """SHA-256 of the instruction text, hex."""
    return hashlib.sha256(policy_text(arm).encode("utf-8")).hexdigest()


def fixture_set_hash(variant: str,
                     revised_pdf_bytes: bytes | None = None) -> str:
    """SHA-256 over the fixture set as one night variant loads it.

    Covers the source texts plus the two quote PDFs (by content hash), so
    a Night B job hashes differently from a Night A job. ``eval``
    arrival-commit nights pass the generated PDF's bytes.
    """
    from app import runner as _runner
    original = _runner.ORIGINAL_PDF.read_bytes()
    revised = (revised_pdf_bytes if revised_pdf_bytes is not None
               else _runner.REVISED_PDF.read_bytes())
    canonical = {
        "texts": fixture_texts(variant),
        "pdfs": {
            "baltic_quote_original.pdf": hashlib.sha256(
                original).hexdigest(),
            "baltic_quote_Q-1187-B.pdf": hashlib.sha256(
                revised).hexdigest(),
        },
    }
    blob = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def provenance_payload(variant: str, arm: str = "supervision",
                       revised_pdf_bytes: bytes | None = None) -> dict:
    """Audit facts for one job: policy, model, effort, fixtures, change."""
    from app.adapter import MODEL
    from app.runner import EFFORT
    lines = changed_lines() if variant == "contrast" else []
    return {
        "variant": variant,
        "policy_hash": policy_hash(arm),
        "model": MODEL,
        "effort": EFFORT,
        "fixture_hash": fixture_set_hash(variant, revised_pdf_bytes),
        "changed_file": NIGHT_B_CHANGED_FILE if variant == "contrast"
        else None,
        "changed_line": " ".join(lines) if lines else None,
    }


def log_provenance(job_id: str, variant: str,
                   virtual_time: str = "21:30",
                   arm: str = "supervision",
                   revised_pdf_bytes: bytes | None = None) -> dict:
    """Append one job's audit facts to its event log."""
    from app.store import append_event
    return append_event(job_id, virtual_time, "provenance",
                        provenance_payload(variant, arm, revised_pdf_bytes))


def results_root() -> Path:
    return Path(__file__).resolve().parent.parent / "results"


def night_b_results_dir() -> Path | None:
    """Results folder the comparison line reads, or None when unknown.

    NIGHT_B_RESULTS_DIR pins one folder (a name under results/ or a path);
    otherwise the latest folder whose results.json holds supervision runs
    of this case wins. After the final frozen runs the same sentence reads
    from the frozen folder through this one config value.
    """
    override = (os.environ.get(NIGHT_B_RESULTS_ENV_VAR) or "").strip()
    if override:
        candidate = Path(override)
        if not candidate.is_absolute():
            candidate = results_root() / candidate
        if (candidate / "results.json").is_file():
            return candidate
        return None
    folders = sorted(
        (d for d in results_root().iterdir()
         if d.is_dir() and (d / "results.json").is_file()),
        key=lambda d: d.name, reverse=True,
    ) if results_root().is_dir() else []
    for folder in folders:
        try:
            payload = json.loads((folder / "results.json").read_text(
                encoding="utf-8"))
        except (OSError, ValueError):
            continue
        records = payload.get("records") or []
        if any(r.get("case") == NIGHT_B_CASE_ID
               and r.get("arm") == "supervision" for r in records):
            return folder
    return None


def comparison_counts(folder: Path | None = None) -> dict | None:
    """k of n for this fixture, from the scorer's observed values.

    k counts runs that held without waking (at least one hold, no
    notification); a premature hold never counts in k. Returns None when
    no supervision runs of this case exist in the folder.
    """
    folder = folder if folder is not None else night_b_results_dir()
    if folder is None:
        return None
    try:
        payload = json.loads((folder / "results.json").read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        return None
    runs = [r for r in (payload.get("records") or [])
            if r.get("case") == NIGHT_B_CASE_ID
            and r.get("arm") == "supervision"]
    if not runs:
        return None
    held = sum(
        1 for r in runs
        if int((r.get("observed") or {}).get("holds") or 0) >= 1
        and not (r.get("observed") or {}).get("notified")
        and int((r.get("observed") or {}).get("premature_holds") or 0) == 0
    )
    return {"k": held, "n": len(runs),
            "development": bool(payload.get("development_run", True)),
            "folder": folder.name}


def comparison_line() -> str:
    """One sentence beside the control, filled from results.json."""
    counts = comparison_counts()
    if counts is None:
        return ""
    runs = "development runs" if counts["development"] else "final runs"
    return (
        f"In our {runs} on this exact fixture it held without waking in"
        f" {counts['k']} of {counts['n']}. When it is unsure it wakes you"
        " instead: that is the safe mistake. It never acts without a"
        " passing check."
    )


def new_night_b_job_id() -> str:
    """A fresh job id for a Night B night (the route redirects to it)."""
    import uuid
    return uuid.uuid4().hex[:12]


def run_fresh_night_b(respond_fn=None, upload_fn=None,
                      delete_fn=None, job_id=None) -> dict:
    """One fresh Night B night from 21:30 (tests use it synchronously).

    A new job id, no reasoning replayed from any earlier run, the same
    policy and model configuration as the hero, under the supervision arm.
    The venue variant comes from the matching eval case file, read here
    through the same override mechanism the harness uses.
    """
    from app import eval_world
    from app import runner as _runner
    case = night_b_case()
    variant = str((case.get("overrides") or {}).get("venue", "hero"))
    with eval_world.patched(case):
        return _runner.run_job(variant=variant, arm="supervision",
                               respond_fn=respond_fn, upload_fn=upload_fn,
                               delete_fn=delete_fn, job_id=job_id)
