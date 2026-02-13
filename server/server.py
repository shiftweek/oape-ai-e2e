"""
FastAPI server that exposes the /oape:api-implement Claude Code skill
via the Claude Agent SDK.

Usage:
    uvicorn api.server:app --reload

Endpoint:
    GET /api-implement?ep_url=<enhancement-pr-url>&cwd=<operator-repo-path>
"""

import json
import logging
import os
import re
import traceback
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)


with open("config.json") as cf:
    config_json_str = cf.read()
CONFIGS = json.loads(config_json_str)


app = FastAPI(
    title="OAPE Operator Feature Developer",
    description="Invokes the /oape:api-implement Claude Code command to generate "
    "controller/reconciler code from an OpenShift enhancement proposal.",
    version="0.1.0",
)

EP_URL_PATTERN = re.compile(
    r"^https://github\.com/openshift/enhancements/pull/\d+/?$"
)

# Resolve the plugin directory (repo root) relative to this file.
# The SDK expects the path to the plugin root (containing .claude-plugin/).
PLUGIN_DIR = str(Path(__file__).resolve().parent.parent / "plugins" / "oape")
print(PLUGIN_DIR)

CONVERSATION_LOG = Path("/tmp/conversation.log")

conv_logger = logging.getLogger("conversation")
conv_logger.setLevel(logging.INFO)
_handler = logging.FileHandler(CONVERSATION_LOG)
_handler.setFormatter(logging.Formatter("%(message)s"))
conv_logger.addHandler(_handler)


@app.get("/api-implement")
async def api_implement(
    ep_url: str = Query(
        ...,
        description="GitHub PR URL for the OpenShift enhancement proposal "
        "(e.g. https://github.com/openshift/enhancements/pull/1234)",
    ),
    cwd: str = Query(
        default="",
        description="Absolute path to the operator repository where code "
        "will be generated. Defaults to the current working directory.",
    ),
):
    """Generate controller/reconciler code from an enhancement proposal."""

    # --- Validate EP URL ---
    if not EP_URL_PATTERN.match(ep_url.rstrip("/")):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid enhancement PR URL. "
                "Expected format: https://github.com/openshift/enhancements/pull/<number>"
            ),
        )

    # --- Resolve working directory ---
    working_dir = cwd if cwd else os.getcwd()
    if not os.path.isdir(working_dir):
        raise HTTPException(
            status_code=400,
            detail=f"The provided cwd is not a valid directory: {working_dir}",
        )

    # --- Build SDK options ---
    options = ClaudeAgentOptions(
        system_prompt=(
            "You are an OpenShift operator code generation assistant. "
            "Execute the oape:api-implement plugin with the provided EP URL. "
        ),
        cwd=working_dir,
        permission_mode="bypassPermissions",
        allowed_tools=CONFIGS['claude_allowed_tools'],
        plugins=[{"type": "local", "path": PLUGIN_DIR}],
    )

    # --- Run the agent ---
    output_parts: list[str] = []
    conversation: list[dict] = []
    cost_usd = 0.0

    def _log(role: str, content, **extra):
        entry = {"role": role, "content": content, **extra}
        conversation.append(entry)
        conv_logger.info(f"[{role}] {content}")

    conv_logger.info(f"\n{'=' * 60}\n[request] ep_url={ep_url}  cwd={working_dir}\n{'=' * 60}")

    try:
        async for message in query(
            prompt=f"/oape:api-implement {ep_url}",
            options=options,
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        output_parts.append(block.text)
                        _log("assistant", block.text)
                    else:
                        _log(f"assistant:{type(block).__name__}",
                             json.dumps(getattr(block, "__dict__", str(block)), default=str))
            elif isinstance(message, ResultMessage):
                cost_usd = message.total_cost_usd
                if message.result:
                    output_parts.append(message.result)
                _log("result", message.result, cost_usd=cost_usd)
            else:
                _log(type(message).__name__,
                     json.dumps(getattr(message, "__dict__", str(message)), default=str))
    except Exception as exc:
        conv_logger.info(f"[error] {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {exc}")

    conv_logger.info(f"[done] cost=${cost_usd:.4f}  parts={len(output_parts)}\n")

    return {
        "status": "success",
        "ep_url": ep_url,
        "cwd": working_dir,
        "output": "\n".join(output_parts),
        "cost_usd": cost_usd,
    }
