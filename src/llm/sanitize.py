"""Detect and strip leaked Gemini tool-call scaffolding from model output.

Gemini Flash intermittently fails to emit a structured function call and
instead dumps the call — together with its private chain-of-thought — into the
message TEXT, using its internal tool-use grammar: a ```tool_code fence,
`default_api.<tool>(...)` print statements, and a `thought` reasoning block.
That text is NEVER a valid reply — shipping it leaks our internal tool names
and the model's reasoning to the user (an information-disclosure bug).

LINE replies are one-shot (a reply_token can't be recalled, no streaming), so
the only safe place to catch this is BEFORE the single send. This module is the
shared primitive behind three layers of defense:
  1. client._is_usable — a leaked turn is treated as an unusable response and
     re-sampled while retry attempts remain, so the fix happens before the
     handler ever sees it (self-healing, user never notices).
  2. handler — if every attempt still leaks, the turn is discarded and routed
     to the empty-response fallback rather than shipped.
  3. handler send chokepoint — strip any residual scaffolding as a last resort.

`default_api.`, ```tool_code and ```tool_outputs never occur in real fitness
replies, so matching them carries no false-positive risk.
"""

import re

# Any one of these markers means the text is leaked scaffolding, not an answer.
_SCAFFOLD_MARKER_RE = re.compile(
    r"```\s*tool_(?:code|outputs)\b"  # fenced tool block opener
    r"|^\s*tool_(?:code|outputs)\s*$"  # bare label line (fence already stripped)
    r"|\bdefault_api\.",  # synthetic namespace: print(default_api.foo(...))
    re.MULTILINE,
)

# Whole ```tool_code ... ``` / ```tool_outputs ... ``` fenced blocks, including
# the unterminated case where the closing fence never arrives (run to EOF).
_SCAFFOLD_BLOCK_RE = re.compile(
    r"^```\s*tool_(?:code|outputs)\b[^\n]*\n.*?(?:^```[^\n]*\n?|\Z)",
    re.MULTILINE | re.DOTALL,
)
# Residual scaffold lines: a synthetic-namespace call or a bare label.
_SCAFFOLD_LINE_RE = re.compile(
    r"^.*\bdefault_api\.[^\n]*$\n?|^\s*tool_(?:code|outputs)\s*$\n?",
    re.MULTILINE,
)


def contains_tool_scaffolding(text: str) -> bool:
    """Whether the model dumped its tool-call grammar into the reply text.

    When true the whole turn is leaked scaffolding, not an answer: callers must
    re-sample or discard it rather than ship it.
    """
    return bool(_SCAFFOLD_MARKER_RE.search(text))


def strip_model_scaffolding(text: str) -> str:
    """Strip leaked Gemini tool-call scaffolding from outbound text.

    Last line of defense at the send chokepoint: even if a code path forgets to
    screen a turn with contains_tool_scaffolding, no ```tool_code block or
    default_api.* line reaches the user. Runs BEFORE markdown stripping so the
    fences are still intact to anchor block removal.
    """
    text = _SCAFFOLD_BLOCK_RE.sub("", text)
    text = _SCAFFOLD_LINE_RE.sub("", text)
    return text
