# Evaluation cases

12 case files. Each holds: `id`, `title`, `type` (`decision_only` |
`complete_job`), `decision_owner` (`model` | `app`), `differs_from_hero` (the
short list of facts that differ from the hero world), `overrides` (applied
in memory at load time by `app/eval_world.py`; fixture files on disk are
never touched), and `expected` (outcome in plain `words` plus
machine-checkable `predicates` on the app's event log).

Note: AGENTS.md names the 12 cases but contains no verbatim outcome
definitions, so there was nothing to quote from it. The `words` below quote
SCENARIO.md verbatim instead: the wake rule ("Wake me only if waiting until
07:00 would lose the last route with verified on-time delivery, you've
checked what you can check, and my answer is the only thing missing."), the
no-permission card line ("Your answer alone places nothing. Approve this
exact request to place the hold."), and the gateway rules. Predicate names
the scorer understands: `notified`, `notified_at_lte`, `holds`,
`drafts_gte`, `hold_request_items_gte`, `portal_errors_gte`,
`no_effect_without_permission`.

Override keys: `venue` (`hero` | `contrast`), `brief` (`hero` |
`no_permission`), `fixture_replacements` (old/new text pairs applied to the
named fixture in memory), `decision_facts` (merged into
`decision_facts.json` in memory), `revised_time` (virtual time of the Q-1187-B
event), `revised_pdf` (`hero` | `arrival_commits`), `owner_answer`
(`{choice, time}` or `null`), `portal` (`ok` | `error_once`).

The eight decision-only cases are four must-wake / no-wake pairs (timing,
evidence, alternatives, necessity). The four complete-job cases are W1-W4.
