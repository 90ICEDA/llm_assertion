# Copyright (c) 2025, NVIDIA CORPORATION & AFFILIATES.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import json
import os
from pathlib import Path
from types import SimpleNamespace

from config import FLAGS
from saver import saver


def get_llm(model_name: str, **kwargs):
    """
    Create a lightweight LLM handle that supports local Qwen deployment through:
    1. Ollama (`llm_engine_type="ollama"`)
    2. OpenAI-compatible endpoints such as vLLM (`llm_engine_type="openai_compatible"`)
    """
    engine = getattr(FLAGS, 'llm_engine_type', 'ollama')
    model_kwargs = dict(kwargs or {})

    if engine == 'ollama':
        import ollama

        base_url = model_kwargs.get('base_url', 'http://127.0.0.1:11434')
        client = ollama.Client(host=base_url)
    elif engine in {'openai', 'openai_compatible'}:
        from openai import OpenAI

        base_url = model_kwargs.get('base_url')
        api_key = model_kwargs.get('api_key', os.environ.get('OPENAI_API_KEY', 'EMPTY'))
        client = OpenAI(base_url=base_url, api_key=api_key)
    else:
        raise ValueError(
            f"Unsupported llm_engine_type={engine}. "
            "Use 'ollama' or 'openai_compatible'."
        )

    return SimpleNamespace(
        engine=engine,
        model_name=model_name,
        client=client,
        kwargs=model_kwargs,
    )


def llm_inference(llm_agent, prompt: str, tag: str) -> str:
    """
    Execute a single chat completion and persist the prompt/response pair.
    """
    system_prompt = llm_agent.kwargs.get(
        'system_prompt',
        (
            "You are an expert hardware verification engineer. "
            "Write precise SystemVerilog assertions and stay faithful to the given spec and RTL context."
        ),
    )

    if llm_agent.engine == 'ollama':
        options = {}
        if 'temperature' in llm_agent.kwargs:
            options['temperature'] = llm_agent.kwargs['temperature']
        if 'num_ctx' in llm_agent.kwargs:
            options['num_ctx'] = llm_agent.kwargs['num_ctx']

        response = llm_agent.client.chat(
            model=llm_agent.model_name,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': prompt},
            ],
            options=options if options else None,
        )
        text = response['message']['content']

    elif llm_agent.engine in {'openai', 'openai_compatible'}:
        request_kwargs = {
            'model': llm_agent.model_name,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': prompt},
            ],
        }
        if 'temperature' in llm_agent.kwargs:
            request_kwargs['temperature'] = llm_agent.kwargs['temperature']
        if 'max_tokens' in llm_agent.kwargs:
            request_kwargs['max_tokens'] = llm_agent.kwargs['max_tokens']

        response = llm_agent.client.chat.completions.create(**request_kwargs)
        text = response.choices[0].message.content or ""

    else:
        raise ValueError(f"Unsupported engine: {llm_agent.engine}")

    _log_llm_interaction(tag, prompt, text)
    return text.strip()


def _log_llm_interaction(tag: str, prompt: str, response: str) -> None:
    log_path = Path(saver.logdir) / 'llm_interactions.txt'
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f"\n\n{'=' * 80}\n")
        f.write(f"Interaction Type: {tag}\n")
        f.write(f"{'=' * 80}\n")
        f.write("Prompt:\n")
        f.write(prompt)
        f.write("\n\nResponse:\n")
        f.write(response)
        f.write("\n")

    metadata_path = Path(saver.logdir) / 'llm_backend.json'
    if not metadata_path.exists():
        llm_summary = {
            'llm_engine_type': getattr(FLAGS, 'llm_engine_type', None),
            'llm_model': getattr(FLAGS, 'llm_model', None),
            'llm_args': getattr(FLAGS, 'llm_args', {}),
        }
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(llm_summary, f, indent=2)
