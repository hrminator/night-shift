# Night Shift — builder brief (WHAT)

You are the only coding agent on this project. The owner directs you; a planning assistant wrote this brief and the scenario, and that is disclosed in the README. You decide the HOW. Push back on anything here that is a bad idea; say so before building it.

## What this is

Night Shift is an overnight manager agent for a small business owner. At 21:30 the owner hands over one job with a brief and goes to bed. The agent (Muse Spark 1.3 through the Meta Model API) works the job through the night on a virtual clock. For every step it decides: act under a standing permission, park it for the 07:00 review, wake the owner with evidence, or block it. In the morning the owner finds a page: what was done, what needs a decision, exact messages awaiting approval, and what could not be verified.

The product claim, in one line: **the agent interrupts you only when the evidence says it must, and nothing leaves the building without your permission or your approval of the exact text.**

Submission for the Meta Global AI Developer Hackathon, Indie track, theme "Build for Your World". Public repo, new work only. A 3-minute video, this repo and a live URL are judged on Impact, Use of Meta AI Tooling, Technical Depth & Execution, and Demo.

## The rule above the desk

**One job, one night, one question, one hold.** If it will not appear in the video, the results or the live URL, it waits. Nothing new after the freeze on Sat Oct 31.

## The loop (never cut)

question -> owner's answer -> resume from the saved point -> authorized simulated effect -> morning page

The scenario is in `SCENARIO.md`. Read it before anything else.

## Non-negotiables

1. **Code enforces permissions, not the model.** Every outgoing action passes a gateway that checks permission, target, fields, terms, time, sources, privacy and once-only, and logs each check. Attempts and effects are logged separately.
2. **The owner's answer is information. The brief's standing permission is authority.** An answer alone never authorizes anything. Four separate log records: the answer, the permission used, the gateway result, the effect.
3. **Approvals cover one exact version (content + recipient), once,** valid 30 minutes or until the item's deadline, whichever is first. Editing a draft voids its approval. Enforced in code, with a test.
4. **Every effect has a unique operation id,** inserted in the same transaction as the effect record. Retries and double clicks return the existing record.
5. **Untrusted content can never create a permission or an approval.** Supplier pages are data.
6. **Deadline arithmetic is code, not the model.** Cutoff 02:00, answer due 01:50, latest safe notification 01:30. The agent notifies as soon as the decision becomes necessary.
7. **A hold never becomes an order by the agent.** The owner approves the order; after the hold lapses at 09:00 that approval is refused.
8. **Encrypted reasoning replay.** `store:false`, `include:["reasoning.encrypted_content"]`, reasoning items sent back intact and in order with the messages and each tool call next to its result. Resend instructions, tools and effort on every call. Never `previous_response_id`. If a resume gets HTTP 400, drop the reasoning items whole, resume from messages and tool results, and log that it did.
9. **Durable task records live outside the model's reasoning:** append-only event log in SQLite (WAL). Status and lock tables are derived and may be updated. Events are never edited.
10. **Everything simulated is labelled where it appears:** "Simulated supplier system", "Simulated delivery". Never call a generated PDF "scanned".
11. **Log every request and response, minus secrets,** including the `model` field each response reports.

## Stack (proposal; you decide)

Python 3.12, FastAPI, server-rendered pages with HTMX polling every 2 s. SQLite WAL, one process, run lock, async worker pool of 2 concurrent model calls. Responses API, `muse-spark-1.3`, standard tier. Upload each PDF once and send by file id. Tools: `read_source`, `record_claim` (source, version, quoted anchor), `record_decision` (wake / no wake / act under permission / wait for morning, with reason and evidence), `ask_owner`, `submit_hold`, `propose_message`. `tool_choice:"auto"` only; if the model answers in plain text, nudge once, then mark the step failed and record it. `max_output_tokens` and tool-call limits on every call. Effort per call type: extraction vs decision turn.

Hosting: always-on small server on the owner's personal account (Fly.io with a volume, or Hetzner), Docker + Caddy. No serverless.

## Day gates (Oslo time)

- **Tue Oct 27:** repo public with LICENSE, PROVENANCE.md, BUILDLOG.md, this file. Hello page deployed. Responses adapter with encrypted replay. One real Spark call reads Baltic's revised quote and Vestland's portal record and records a claim with its quoted source, shown on a deployed page. Test a true image-only scan vs a generated PDF styled as a scan; keep what Spark reads reliably. Log reasoning tokens, seconds and cost per effort level (minimal, low, medium). Measure whether a PDF by file id is billed again on each replayed turn. All fixtures written. Save today's encrypted reasoning items.
- **Wed Oct 28:** ONE plain-screen scenario completes question -> answer -> resume -> authorized simulated effect. Ugly is fine. Start from a fixed single decision turn. Task state, saved point, resume, the gateway with the standing-hold check, simulated portal acknowledgement, simulated outbox with operation ids. Contract tests 3, 4, 5.
- **Thu Oct 29:** same loop reliable at the public URL (three clean runs in a row). The scheduled 00:38 event, the six named checks, the decision record. Restart/resume, approval expiry, visitor copy. The one product screen. Contract tests 1, 2, 6, 7, 11. Replay from Oct 27's saved reasoning items.
- **Fri Oct 30:** runtime limits (bounded concurrency, spend cap, tool-call limits), contract tests 8, 9, 10. Evaluation integration: 12 case files and a scorer reading the app's own event log. The two contrast runs.
- **Sat Oct 31:** fixes only. Freeze. Rough video.

If the loop is not working by Wed evening, simplify in this order: fixed sequence of turns; resume only on a button press; one draft instead of three. Reserve hours go to the loop, never to features.

## Contract tests (pure code, no model)

1. Changing a draft's content or recipient voids its approval.
2. Expired approval rejected (older than 30 min, or after the item's deadline; Vestland order at 09:01 refused).
3. The owner's factual answer alone never places a hold or sends anything.
4. A hold outside the permission is refused: wrong portal, extra field, cost above 0, binding terms, answer after 01:50, submit after 02:00, a second hold.
5. Double clicks and retries never create a second effect.
6. A restart mid-night resumes the right job at the right step.
7. Text on a supplier page cannot create a permission or an approval.
8. The spend cap holds with several calls in flight.
9. A turn with no tool call, or too many, is handled and logged.
10. A tool call whose arguments fail the schema is refused and logged as malformed.
11. Two visitor resumes of the same saved point produce two separate jobs, each with exactly one hold; the recorded run is unchanged.

## Live product (one screen)

Opens on the replay of the recorded hero run (real Spark calls, labelled with date and model), plays 60-90 s, stops at the question. The visitor taps an answer; that copies the saved job into a new job with its own ids and outbox and resumes live. The simulated hold comes back, drafts update, the visitor approves one draft into the on-page outbox and can edit a word to see the approval flip. Below: "How it decided" (checks, source passage, stated reason). Guard: at most 2 live resumes at once, a daily spend cap, recorded response when the cap is hit, labelled.

## Repo hygiene

- No `.claude/`, `.codex/`, `MEMORY.md`, secrets or `.env` in the repo. Keys come from the environment.
- Two separate API keys: live site and evaluation.
- PROVENANCE.md lists every dependency, font, asset and fixture and where it came from. BUILDLOG.md gets a few lines per session: what was built, what failed, what was cut.
- Commit often, with plain messages. Commit timestamps are evidence that the work is new.
- Everything fictional stays fictional: no real companies, no real people, no personal data.

## Working on this Windows machine

- Your sandboxed shell starts in a system folder, not the repo. Begin every shell command with `Set-Location C:\Users\herma\night-shift` (or use absolute paths), otherwise git and relative paths fail with "not a git repository".
- Available: Python, `uv` (C:\Python313\Scripts\uv.exe), Docker Desktop, Node. `flyctl` is not installed yet; install it with the official PowerShell installer when you reach the deploy step.
- Keep the virtual environment inside the repo (`.venv`), never in a temp folder.
- The API keys are in the user environment as `NIGHT_SHIFT_API_KEY_LIVE` (for the deployed site, set as a Fly secret) and `NIGHT_SHIFT_API_KEY_EVAL` (local runs and the evaluation). Read them from the environment; never write them into files or print them. Never set `META_API_KEY`, because that redirects Muse Code's own billing.
- Learned Tue Oct 27: call uv by full path `C:\Python313\Scripts\uv.exe` when `uv` is not on PATH; local interpreter is Python 3.13.5. The files endpoint ignores `expires_after` (uploads return no expiry), so every script that uploads must delete its files after use. Medium effort needs `max_output_tokens` of at least 2048 (1024 truncates the call with empty text). Repo files use CRLF: multi-line exact-match edits fail, so match a single line. Start Docker Desktop before any `docker` command (the engine may be stopped). Host port 8080 is taken by another local service; test containers on a free host port (e.g. `-p 8123:8080`). Prefer small `python` script files over `python -c` one-liners; PowerShell quoting mangles brackets and quotes.

## Out of scope (do not build)

Second worker lane, separate research loop, other models in the product or results, scoreboard or counterfactual pages, cache studies, raw reasoning displays, voice, real web fetching, native web search, background mode, batch, tool_search, images, SAM, Glimmer, messaging integrations, CRM, undo, user accounts, free-text briefs, QR codes.
