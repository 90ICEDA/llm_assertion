#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DEFAULT_TIMEOUT_SEC = 600
PLACEHOLDER_SNIPPETS = [
    "你的",
    "api_key",
    "model",
    "replace_me",
    "your_",
    "<api",
    "<model",
]


def looks_like_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return True
    return any(snippet in lowered for snippet in PLACEHOLDER_SNIPPETS)


def resolve_api_key(cli_value: str | None) -> str:
    for candidate in [
        cli_value,
        os.environ.get("QWEN_API_KEY"),
        os.environ.get("DASHSCOPE_API_KEY"),
    ]:
        if candidate and candidate.strip():
            value = candidate.strip()
            if looks_like_placeholder(value):
                raise RuntimeError(
                    "QWEN_API_KEY/DASHSCOPE_API_KEY is still a placeholder. "
                    "Replace it with your real API key."
                )
            try:
                value.encode("latin-1")
            except UnicodeEncodeError as e:
                raise RuntimeError(
                    "API key contains non-Latin-1 characters. This usually means you pasted "
                    "a placeholder like '你的API_KEY' instead of a real key."
                ) from e
            return value
    raise RuntimeError(
        "Missing Qwen API key. Set QWEN_API_KEY or DASHSCOPE_API_KEY, "
        "or pass --api-key."
    )


def resolve_base_url(cli_value: str | None) -> str:
    for candidate in [
        cli_value,
        os.environ.get("QWEN_BASE_URL"),
        os.environ.get("DASHSCOPE_BASE_URL"),
        os.environ.get("OPENAI_BASE_URL"),
    ]:
        if candidate and candidate.strip():
            return candidate.strip().rstrip("/")
    return DEFAULT_BASE_URL


def resolve_model(cli_value: str | None) -> str:
    for candidate in [
        cli_value,
        os.environ.get("QWEN_MODEL"),
        os.environ.get("DASHSCOPE_MODEL"),
    ]:
        if candidate and candidate.strip():
            value = candidate.strip()
            if looks_like_placeholder(value):
                raise RuntimeError(
                    "QWEN_MODEL/DASHSCOPE_MODEL is still a placeholder. "
                    "Replace it with your real Qwen model ID."
                )
            return value
    raise RuntimeError(
        "Missing Qwen model name. Set QWEN_MODEL or DASHSCOPE_MODEL, "
        "or pass --model."
    )


def read_prompt_text(prompt_file: str) -> str:
    return Path(prompt_file).resolve().read_text(encoding="utf-8")


def post_chat_completion(
    *,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    temperature: float,
    timeout_sec: int,
) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "stream": False,
    }
    endpoint = f"{base_url}/chat/completions"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(
            f"Qwen API HTTP {e.code} calling {endpoint}: {detail}"
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Cannot reach Qwen API at {endpoint}: {e}"
        ) from e

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Qwen API returned invalid JSON: {body[:500]}"
        ) from e

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(
            f"Qwen API response missing choices[0].message.content: {body[:1000]}"
        ) from e

    if isinstance(content, list):
        # Some OpenAI-compatible providers may return multimodal content parts.
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
        content = "\n".join(part for part in text_parts if part)

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(
            f"Qwen API returned empty content: {body[:1000]}"
        )
    return content


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Call a Qwen OpenAI-compatible API with a prompt file and print the text response."
    )
    parser.add_argument("--prompt-file", required=True, help="Prompt file path.")
    parser.add_argument("--api-key", help="Qwen/DashScope API key.")
    parser.add_argument("--base-url", help="OpenAI-compatible base URL.")
    parser.add_argument("--model", help="Qwen model name.")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    args = parser.parse_args()

    prompt = read_prompt_text(args.prompt_file)
    api_key = resolve_api_key(args.api_key)
    base_url = resolve_base_url(args.base_url)
    model = resolve_model(args.model)

    text = post_chat_completion(
        api_key=api_key,
        base_url=base_url,
        model=model,
        prompt=prompt,
        temperature=args.temperature,
        timeout_sec=args.timeout_sec,
    )
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
