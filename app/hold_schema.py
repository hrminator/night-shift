"""The submit_hold tool contract: one explicit JSON schema.

The model decides act_under_permission and then fills this payload. Every
property is required, typed, and described in one line, so the gateway never
has to be discovered by trial. Shape errors are refused as malformed (naming
the exact property); meaning errors are refused by the gateway (naming the
exact key). The gateway keeps its checks; it reads this payload through
``normalize_hold_args`` / ``normalize_hold_sources`` first.
"""

from __future__ import annotations

import re

HOLD_REQUIRED = [
    "portal", "action", "product", "quantity", "print_file", "address",
    "delivery_window", "ordering_contact", "recipient_can_receive", "cost",
    "binding", "hold_ends", "sources",
]

SOURCE_REQUIRED = [
    "recipient_can_receive", "route", "window", "ordering_contact",
    "print_file",
]

#: One-line expected shape per key. Gateway refusals and schema errors quote
#: these, so one correction is enough.
HOLD_SHAPE = {
    "portal": '"portal": "vestland_portal"',
    "action": '"action": "capacity_hold"',
    "product": '"product": "100 tote bags with logo"',
    "quantity": '"quantity": 100',
    "print_file": '"print_file": "fjord-fern-logo-print.pdf"',
    "address": '"address": "Sjøsalen, Sjøgaten 5, 5003 Bergen (fictional)"',
    "delivery_window": '"delivery_window": "Wed Nov 11 08:00-12:00"',
    "ordering_contact": '"ordering_contact": "Kari Strandli, studio coordinator,'
    ' orders@fjord-fern.example.com, +47 22 00 11 22"',
    "recipient_can_receive": '"recipient_can_receive": true',
    "cost": '"cost": 0',
    "binding": '"binding": false',
    "hold_ends": '"hold_ends": "09:00"',
    "sources": '"sources": {"recipient_can_receive": {"kind": "owner_answer",'
    ' "id": 7}, "route": {"kind": "portal", "version": 1},'
    ' "window": {"kind": "portal", "version": 1},'
    ' "ordering_contact": {"kind": "studio_file"},'
    ' "print_file": {"kind": "studio_file"}}',
}

SUBMIT_HOLD_PARAMETERS = {
    "type": "object",
    "properties": {
        "portal": {
            "type": "string",
            "enum": ["vestland_portal"],
            "description": 'Always "vestland_portal": the standing permission'
            " covers only Vestland Tekstil's order portal.",
        },
        "action": {
            "type": "string",
            "enum": ["capacity_hold"],
            "description": 'Always "capacity_hold": the permission covers one'
            " capacity hold, never an order.",
        },
        "product": {
            "type": "string",
            "description": 'Product line, e.g. "100 tote bags with logo".',
        },
        "quantity": {
            "type": "integer",
            "description": "Bag count for this job: always the integer 100.",
        },
        "print_file": {
            "type": "string",
            "description": "Print file name exactly as in the studio file:"
            " fjord-fern-logo-print.pdf.",
        },
        "address": {
            "type": "string",
            "description": "Exactly one address from the owner's list: the"
            " Oslo office or Sjøsalen, Sjøgaten 5, 5003 Bergen.",
        },
        "delivery_window": {
            "type": "string",
            "description": 'Vestland van window: "Wed Nov 11 08:00-12:00".',
        },
        "ordering_contact": {
            "type": "string",
            "description": "Ordering contact exactly as in the studio file"
            " (name, role, email, phone).",
        },
        "recipient_can_receive": {
            "type": "boolean",
            "description": "Always true: confirms the recipient can receive"
            " in the window.",
        },
        "cost": {
            "type": "number",
            "description": "Always the number 0: the hold costs nothing.",
        },
        "binding": {
            "type": "boolean",
            "description": "Always false: the hold is non-binding (no order,"
            " no payment).",
        },
        "hold_ends": {
            "type": "string",
            "description": 'Hold end time as HH:MM at or before 09:00, e.g.'
            ' "09:00".',
        },
        "sources": {
            "type": "object",
            "description": "Evidence pointer for every stated fact: the"
            " claim and answer ids come from earlier tool results.",
            "properties": {
                "recipient_can_receive": {
                    "type": "object",
                    "description": "Receipt confirmation: {\"kind\":"
                    ' "owner_answer", "id": <owner_answer event id>} or'
                    ' {"kind": "claim", "id": <venue-confirmation claim id>}.',
                    "properties": {
                        "kind": {"type": "string",
                                 "enum": ["claim", "owner_answer"]},
                        "id": {"type": "integer"},
                    },
                    "required": ["kind", "id"],
                    "additionalProperties": False,
                },
                "route": {
                    "type": "object",
                    "description": 'Vestland route source: {"kind": "portal",'
                    ' "version": 1}.',
                    "properties": {
                        "kind": {"type": "string", "enum": ["portal"]},
                        "version": {"type": "integer"},
                    },
                    "required": ["kind", "version"],
                    "additionalProperties": False,
                },
                "window": {
                    "type": "object",
                    "description": 'Van window source: {"kind": "portal",'
                    ' "version": 1}.',
                    "properties": {
                        "kind": {"type": "string", "enum": ["portal"]},
                        "version": {"type": "integer"},
                    },
                    "required": ["kind", "version"],
                    "additionalProperties": False,
                },
                "ordering_contact": {
                    "type": "object",
                    "description": 'Contact source: {"kind": "studio_file"}'
                    " (fixtures/studio.json).",
                    "properties": {
                        "kind": {"type": "string",
                                 "enum": ["studio_file"]},
                    },
                    "required": ["kind"],
                    "additionalProperties": False,
                },
                "print_file": {
                    "type": "object",
                    "description": 'Print-file source: {"kind": "studio_file"}'
                    " (fixtures/studio.json).",
                    "properties": {
                        "kind": {"type": "string",
                                 "enum": ["studio_file"]},
                    },
                    "required": ["kind"],
                    "additionalProperties": False,
                },
            },
            "required": list(SOURCE_REQUIRED),
            "additionalProperties": False,
        },
    },
    "required": list(HOLD_REQUIRED),
    "additionalProperties": False,
}

_HOLD_ENDS_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _source_errors(sources: dict) -> list[str]:
    errors: list[str] = []
    for key in SOURCE_REQUIRED:
        if key not in sources:
            errors.append(f'missing "sources.{key}": expected {HOLD_SHAPE["sources"]}')
    for key in sources:
        if key not in SOURCE_REQUIRED:
            errors.append(f'unexpected "sources.{key}": expected only '
                          f'{", ".join(SOURCE_REQUIRED)}')
    gotten = sources.get("recipient_can_receive")
    if isinstance(gotten, dict):
        kind, ref = gotten.get("kind"), gotten.get("id")
        if kind not in ("claim", "owner_answer"):
            errors.append('sources.recipient_can_receive.kind must be "claim"'
                          f' or "owner_answer": expected {HOLD_SHAPE["sources"]}')
        if not _is_int(ref):
            errors.append('sources.recipient_can_receive.id must be an integer'
                          f' event id: expected {HOLD_SHAPE["sources"]}')
        if len(gotten) != 2:
            errors.append('sources.recipient_can_receive takes only kind and'
                          f' id: expected {HOLD_SHAPE["sources"]}')
    elif "recipient_can_receive" in sources:
        errors.append('sources.recipient_can_receive must be an object with'
                      f' kind and id: expected {HOLD_SHAPE["sources"]}')
    for key in ("route", "window"):
        gotten = sources.get(key)
        if isinstance(gotten, dict):
            if gotten.get("kind") != "portal":
                errors.append(f'sources.{key}.kind must be "portal":'
                              f' expected {HOLD_SHAPE["sources"]}')
            if not _is_int(gotten.get("version")):
                errors.append(f'sources.{key}.version must be an integer:'
                              f' expected {HOLD_SHAPE["sources"]}')
            if set(gotten) != {"kind", "version"}:
                errors.append(f'sources.{key} takes only kind and version:'
                              f' expected {HOLD_SHAPE["sources"]}')
        elif key in sources:
            errors.append(f'sources.{key} must be an object with kind and'
                          f' version: expected {HOLD_SHAPE["sources"]}')
    for key in ("ordering_contact", "print_file"):
        gotten = sources.get(key)
        if isinstance(gotten, dict):
            if gotten.get("kind") != "studio_file" or set(gotten) != {"kind"}:
                errors.append(f'sources.{key} must be {{"kind":'
                              f' "studio_file"}}: expected {HOLD_SHAPE["sources"]}')
        elif key in sources:
            errors.append(f'sources.{key} must be {{"kind": "studio_file"}}:'
                          f' expected {HOLD_SHAPE["sources"]}')
    return errors


def hold_schema_errors(args: object) -> list[str]:
    """Check a submit_hold payload against the tool schema.

    Returns one error line per bad property, each naming the property and
    its expected shape. An empty list means the shape is well-defined (the
    gateway still checks what the shape means).
    """
    if not isinstance(args, dict):
        return ["arguments must be an object holding the hold payload:"
                f' expected {", ".join(HOLD_REQUIRED)}']
    errors: list[str] = []
    for key in HOLD_REQUIRED:
        if key not in args:
            errors.append(f'missing "{key}": expected {HOLD_SHAPE[key]}')
    for key in args:
        if key not in HOLD_REQUIRED:
            errors.append(f'unexpected "{key}": submit_hold takes only '
                          f'{", ".join(HOLD_REQUIRED)}')
    if args.get("portal") != "vestland_portal":
        if "portal" in args:
            errors.append(f'wrong "portal": expected {HOLD_SHAPE["portal"]}')
    if args.get("action") != "capacity_hold":
        if "action" in args:
            errors.append(f'wrong "action": expected {HOLD_SHAPE["action"]}')
    if "product" in args and (not isinstance(args["product"], str)
                              or not args["product"].strip()):
        errors.append(f'wrong "product": expected {HOLD_SHAPE["product"]}')
    if "quantity" in args and (not _is_int(args["quantity"])
                               or args["quantity"] != 100):
        errors.append(f'wrong "quantity": expected {HOLD_SHAPE["quantity"]}')
    for key in ("print_file", "address", "delivery_window",
                "ordering_contact"):
        if key in args and (not isinstance(args[key], str)
                            or not args[key].strip()):
            errors.append(f'wrong "{key}": expected {HOLD_SHAPE[key]}')
    if "recipient_can_receive" in args and args["recipient_can_receive"] is not True:
        errors.append('wrong "recipient_can_receive":'
                      f' expected {HOLD_SHAPE["recipient_can_receive"]}')
    if "cost" in args and (isinstance(args["cost"], bool)
                           or not isinstance(args["cost"], (int, float))
                           or args["cost"] != 0):
        errors.append(f'wrong "cost": expected {HOLD_SHAPE["cost"]}')
    if "binding" in args and args["binding"] is not False:
        errors.append(f'wrong "binding": expected {HOLD_SHAPE["binding"]}')
    if "hold_ends" in args:
        match = (_HOLD_ENDS_RE.match(args["hold_ends"])
                 if isinstance(args["hold_ends"], str) else None)
        minutes = (int(match.group(1)) * 60 + int(match.group(2))
                   if match else None)
        if minutes is None or minutes > 9 * 60:
            errors.append(f'wrong "hold_ends": expected {HOLD_SHAPE["hold_ends"]}')
    if "sources" in args:
        if isinstance(args["sources"], dict):
            errors.extend(_source_errors(args["sources"]))
        else:
            errors.append(f'wrong "sources": expected {HOLD_SHAPE["sources"]}')
    return errors


def normalize_hold_sources(sources: object) -> object:
    """Translate new evidence pointers to the form the gateway checks.

    {"kind": "owner_answer"|"claim", "id": N} becomes N; {"kind": "portal",
    "version": V} becomes "vestland_portal.json vV". Anything else passes
    through untouched (the gateway ignores contact/file pointers).
    """
    if not isinstance(sources, dict):
        return sources
    out: dict = {}
    for key, value in sources.items():
        if isinstance(value, dict) and "kind" in value:
            kind = str(value.get("kind", "")).lower()
            if kind in ("owner_answer", "claim") and _is_int(value.get("id")):
                out[key] = value["id"]
            elif kind == "portal" and _is_int(value.get("version")):
                out[key] = f'vestland_portal.json v{value["version"]}'
            else:
                out[key] = value
        else:
            out[key] = value
    return out


def normalize_hold_args(args: object) -> dict | None:
    """Translate a submit_hold payload to {"portal", "fields"}.

    Accepts the flat tool payload (portal, action, product, ...) and the
    legacy nested form (portal plus fields). Returns None when neither fits.
    """
    if not isinstance(args, dict):
        return None
    if isinstance(args.get("fields"), dict) and isinstance(
            args.get("portal"), str):
        return {"portal": args["portal"], "fields": dict(args["fields"])}
    if any(key in args for key in HOLD_REQUIRED):
        fields = {key: value for key, value in args.items()
                  if key != "portal"}
        return {"portal": args.get("portal"), "fields": fields}
    return None
