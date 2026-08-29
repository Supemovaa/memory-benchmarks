"""Patch mem0's OpenAI provider to forward extractor thinking mode.

``enable_thinking`` is an extension used by some OpenAI-compatible APIs. The
three-state environment setting keeps the field absent for providers that do
not support it.
"""

from pathlib import Path


TARGET = Path("/usr/local/lib/python3.12/site-packages/mem0/llms/openai.py")

HELPER = '''

def _parse_optional_bool_env(name: str):
    """Parse true/false/none, returning None when the field must be omitted."""
    raw = os.getenv(name)
    if raw is None:
        return None

    value = raw.strip().lower()
    if value == "none":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{name} must be true, false, or none; got {raw!r}")
'''

REQUEST_OPTIONS = '''        enable_thinking = _parse_optional_bool_env("EXTRACTOR_ENABLE_THINKING")
        if enable_thinking is not None:
            extra_body = dict(params.get("extra_body") or {})
            extra_body["enable_thinking"] = enable_thinking
            params["extra_body"] = extra_body
'''


def patch_source(source: str) -> str:
    """Return patched source and fail loudly if the upstream shape changed."""
    if 'enable_thinking = _parse_optional_bool_env("EXTRACTOR_ENABLE_THINKING")' in source:
        return source

    class_anchor = "\nclass OpenAILLM(LLMBase):"
    if class_anchor not in source:
        raise RuntimeError("mem0 OpenAILLM class anchor was not found")
    source = source.replace(class_anchor, HELPER + class_anchor, 1)

    request_anchor = "        response = self.client.chat.completions.create(**params)"
    if request_anchor not in source:
        raise RuntimeError("mem0 OpenAI request anchor was not found")
    return source.replace(request_anchor, REQUEST_OPTIONS + request_anchor, 1)


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    patched = patch_source(source)
    TARGET.write_text(patched, encoding="utf-8")
    print(f"Patched {TARGET}: extractor enable_thinking forwarding")


if __name__ == "__main__":
    main()
