# Plan: Address PR Review Comments

This plan covers the review comments posted on PR #2 and PR #3 (merged into `agentsec-changes`).

---

## PR #3: Normalize strict OpenAI-compatible params

### 1. Add documentation for Mistral URL detection

**File:** `aidefense/runtime/agentsec/patchers/openai.py`  
**Function:** `_normalize_kwargs_for_strict_openai_compat`

**Action:** Expand the docstring to document how Mistral is detected and when normalization applies.

```python
def _normalize_kwargs_for_strict_openai_compat(instance: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize parameters for stricter OpenAI-compatible APIs like Mistral.
    
    Mistral's OpenAI-compatible API rejects some fields that LangChain sends
    (e.g. max_completion_tokens, presence_penalty, frequency_penalty), causing 422 errors.
    
    Provider detection: Checks if client's base_url contains "mistral" (case-insensitive).
    Only applies normalization when targeting Mistral; other providers receive kwargs unchanged.
    """
```

### 2. Add comment for max_tokens vs max_completion_tokens edge case

**File:** `aidefense/runtime/agentsec/patchers/openai.py`  
**Location:** Inside `_normalize_kwargs_for_strict_openai_compat`, before the rewrite logic

**Action:** Add an inline comment explaining the behavior when both keys exist.

```python
# If both max_tokens and max_completion_tokens exist, prefer the completion value
# since LangChain often sends max_completion_tokens for strict APIs.
if "max_completion_tokens" in normalized:
    normalized["max_tokens"] = normalized.pop("max_completion_tokens")
```

### 3. Add unit tests for _normalize_kwargs_for_strict_openai_compat

**File:** `aidefense/tests/agentsec/unit/test_openai_patcher_extended.py`

**Action:** Add a new test class `TestNormalizeKwargsForStrictOpenAICompat` with:

| Test | Description |
|------|-------------|
| `test_mistral_rewrites_max_completion_tokens` | Mistral base_url + `max_completion_tokens` → `max_tokens` |
| `test_mistral_drops_penalty_params` | Mistral + `presence_penalty`/`frequency_penalty` → removed |
| `test_non_mistral_passes_through` | OpenAI base_url → kwargs unchanged |
| `test_no_client_returns_kwargs` | Instance without `_client` → kwargs unchanged |
| `test_mistral_both_max_tokens_replaced` | Mistral + both keys → `max_completion_tokens` wins |

**Implementation notes:**
- Import `_normalize_kwargs_for_strict_openai_compat` from the patcher module
- Use `SimpleNamespace(_client=SimpleNamespace(base_url="..."))` for instance
- Assert on the returned dict

---

## PR #2: Parse raw OpenAI responses before post-call inspection

### 4. Add unit tests for response parsing and content extraction

**File:** `aidefense/tests/agentsec/unit/test_openai_patcher_extended.py`

**Action:** Extend `TestExtractAssistantContent` (or add a new section) for:

| Test | Description |
|------|-------------|
| Raw wrapper with `.parse()` | Response has no `choices`, has `parse()` → returns parsed object; extract content |
| Dict response | `response` is `dict` with `choices[0].message.content` |
| Block-based content (text key) | `content` is `[{"type": "text", "text": "Hello"}]` → "Hello" |
| Block-based content (content key) | `content` is `[{"type": "text", "content": "Hi"}]` (handled in item 5) |
| Multiple blocks | `content` is list of blocks → concatenated with newlines |
| Object blocks with `.text` | Block has `text` attribute (not dict) |

**Implementation notes:**
- May need to import `_content_to_text` and `_resolve_response_for_inspection` if testing them directly
- Or test via `_extract_assistant_content` (integration-style)
- Use `SimpleNamespace` and mocks for raw wrapper

### 5. Handle `content` key in _content_to_text for block-based content

**File:** `aidefense/runtime/agentsec/patchers/openai.py`  
**Function:** `_content_to_text`

**Action:** In the dict block handling, also check for `content` key (some SDKs use it instead of `text`).

```python
if isinstance(block, dict):
    text = block.get("text") or block.get("content")  # Support both keys
    if text:
        parts.append(str(text))
```

This makes the function robust if LangChain or other clients use `{"type": "text", "content": "..."}`.

---

## Execution order

1. **Code changes first** (items 1, 2, 5) — docstrings, comments, and `_content_to_text` enhancement
2. **Tests** (items 3, 4) — add unit tests
3. **Verify** — run `poetry run pytest aidefense/tests -v`

---

## Files to modify

| File | Changes |
|------|---------|
| `aidefense/runtime/agentsec/patchers/openai.py` | Docstring, comment, `_content_to_text` |
| `aidefense/tests/agentsec/unit/test_openai_patcher_extended.py` | New tests for normalization + response parsing |
