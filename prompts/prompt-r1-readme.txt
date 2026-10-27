Read README.md, BUILDLOG.md, PROVENANCE.md, AGENTS.md and results/*/report.md. Prompt R1: the README top screen and consistency. Begin every shell command with Set-Location C:\Users\herma\night-shift and set $env:UV_CACHE_DIR='C:\Users\herma\night-shift\.uv-cache'. Not sandboxed. This prompt changes only documentation and one small script; no product behaviour changes. Commit after each part, do not push, do not deploy, suite green.

Part 1. Publish the prompt files. Create prompts/ in the repo and copy every file matching C:\Users\herma\mgadh\handoff\prompt-*.txt into it, unchanged, plus this file as prompts/prompt-r1-readme.txt. Add prompts/README.md with three lines: these are the exact prompt files that drove Muse Code, in order; API details inside them were copied from Meta's docs; the planning documents they refer to (AGENTS.md, SCENARIO.md) are in the repo root. Do not add any other files from outside the repo.

Part 2. Publish the instruction text. Add scripts/dump_instructions.py that prints the exact instruction text the app sends to the model for each night turn type (read, reassess, resume) and for each arm, with the brief and permission included, and writes it to docs/instructions.md with a heading per turn type and arm. Run it and commit the output. Add a test that the file is in sync with the code (regenerate and compare).

Part 3. DEPLOY.md: move the Fly deployment steps, environment variables (NIGHT_SHIFT_API_KEY_LIVE, NIGHT_SHIFT_API_KEY_EVAL, RUN_TOKEN, DAILY_CAP_USD, RECORDED_JOB, DATA_DIR) and the local run instructions out of README.md into DEPLOY.md. Never print key values.

Part 4. Rewrite README.md to this structure, using the texts below verbatim where given and the repo's real numbers elsewhere (take every number from BUILDLOG.md or results/; write no number you cannot point to). Sections that do not have content yet get one honest line ("not yet: planned for <day>"), never a placeholder like (URL).

Above the fold, in this order:
1. "# Night Shift" and this sentence in italics: An overnight manager on Muse Spark that works your job while you sleep, acts only inside the permission you gave it, and is built to wake you only when the evidence says it must; the results below show how often it gets that right.
2. A line for the GIF: "(12-second film of one night: coming Thu Oct 29)".
3. Links line: Try it live (https://night-shift-demo.fly.dev/) · 3-min video (coming Nov 2) · Results (#results) · How it was built (#built-during-the-hackathon).
4. Three bullets, verbatim: "It changes its mind when the evidence changes." / "It can act, narrowly." / "Measured, not claimed."
5. One italic disclosure line, verbatim: Fictional studio and suppliers · real Muse Spark calls, recorded and replayed at compressed speed; the answer step runs live · supplier systems and mail simulated · built Oct 27–Nov 3, all code written by Muse Code.

Then these sections, in this order, with these headings:
1. "Try it in two minutes": answer the question on the front door (what happens, in three sentences); "change one fact" is coming Fri Oct 30.
2. "One night, minute by minute": a 9-row table, 21:30 to 09:00, taken from SCENARIO.md and the recorded hero run (job id named).
3. "How it works": at most 6 bullets: event log, virtual clock with coded deadlines, the four supervision rules, the gateway's eight checks, approvals bound to exact text with expiry, simulated portal and outbox with operation ids.
4. "How it uses Meta's models": the Responses API with encrypted reasoning replay and the measured resume numbers (first call vs replay input tokens, from BUILDLOG), the drop-and-resume fallback; the image-only page read and how the page was made (rendered by scripts/make_fixtures.py, not a scan); effort per call type; tool calling with schema refusal; Muse Code as the builder with a link to prompts/. Put links to the exact source files that call the Meta API (app/adapter.py and the scripts) at the top of this section. Note that the grounding call and the cache key are planned for Wed Oct 28 and not built yet.
5. "Results": keep the pilot table that exists, labelled development runs, with the misses stated in words under it, and a line "Final runs: 12 situations × 2 arms × 3 runs on the frozen tag, planned for Sat Oct 31". Add the contrast line, verbatim: "Contrast runs so far: 1 of 2 fresh contrast runs placed the hold itself without waking the owner; the other woke anyway (job ids: 37f34f71d9df, 36e41552448b)."
6. "What real owners said": "Not yet: three to five small-business owners will be asked Thu–Sat and quoted by role, with permission. The true count will be reported."
7. "Known failures and variance": the contrast disagreement; the pilot's needless wakes and duplicate notifications with case names; every post-pilot fix with its date (the duplicate-question rule and the never-ask-after-deadline rule, Oct 27); the removed early instruction tune ("the guaranteed van IS the verified route", removed Oct 27; the neutral wording woke on its first run); the model-judgment miss on alternatives_no_wake, untuned.
8. "What's real, computed and simulated": the three-tag legend MUSE SPARK / CODE / SIMULATED and one line per item.
9. "Limitations": one constructed supplier world; a compressed clock; an image-only PDF made by our script, not a real scan; the gateway cannot judge "only way".
10. "Built during the hackathon": dates, links to PROVENANCE.md, BUILDLOG.md, the git history, and this paragraph verbatim, with the two bracketed parts left as they are for now:
    Night Shift was built during the hackathon, Oct 27–Nov 3, 2026, by one person with AI tools. All code, tests and fixtures were written by Muse Code (muse-spark-1.3), driven by the prompt files in prompts/. A general AI assistant (Claude) wrote and sent those prompt files and the README prose, and ran Muse Code headless; API details in the prompts are copied from Meta's docs and labelled as such. I set direction, made every decision and reviewed the results. Plain-language design documents written before Oct 27 were used as inputs; no pre-event code is in this repository. The studio, suppliers, venue, documents and contacts are fictional, with invented names. The revised quote is an image-only PDF rendered by our fixture script, not a scan of a real document, and it arrives as an injected test event. The supplier portal and mail are simulated. The model calls on the front door are real Muse Spark calls, recorded on [date of the recorded run] and replayed at compressed speed; the answer step runs live. [Opening-shot sentence to be added after the video is recorded.]
11. "Run it locally and deploy": one line linking DEPLOY.md.
12. "Repository map": one line per top-level folder and key file.
13. "License": MIT.

Wording rules everywhere: "built to wake you only when it must"; "all code commits are Muse Code's", never "every commit"; "one person with AI tools", never a bare "solo". Remove every mention of "Day 1: hello page", "redeploy pending", "Video: (URL)" and "do not run them before then". Status and Results must say the same thing about the contrast runs.

Part 5. PROVENANCE.md: make sure the "Who and what built this" section uses the same authorship wording as the README paragraph, and that every fixture and dependency added so far is listed.

End with a short summary: what changed, the commit list, and any number you could not source from the logs (leave such a number out rather than guess).
