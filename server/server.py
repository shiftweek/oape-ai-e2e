"""
FastAPI server that exposes OAPE Claude Code skills via the Claude Agent SDK.

Usage:
    uvicorn server:app --reload

Endpoints:
    GET  /                                    - Homepage with submission form
    POST /submit                              - Submit a job (returns job_id)
    GET  /status/{job_id}                     - Poll job status
    GET  /stream/{job_id}                     - SSE stream of agent conversation
    GET  /api/v1/oape-api-implement?ep_url=.. - Synchronous API-implement endpoint
"""

import asyncio
import json
import os
import re
import uuid

from fastapi import FastAPI, HTTPException, Query, Form
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

from agent import run_agent, SUPPORTED_COMMANDS


app = FastAPI(
    title="OAPE Operator Feature Developer",
    description="Invokes OAPE Claude Code commands to generate "
    "controller/reconciler code from an OpenShift enhancement proposal.",
    version="0.1.0",
)

EP_URL_PATTERN = re.compile(
    r"^https://github\.com/openshift/enhancements/pull/\d+/?$"
)

# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------
jobs: dict[str, dict] = {}


def _validate_ep_url(ep_url: str) -> None:
    """Raise HTTPException if ep_url is not a valid enhancement PR URL."""
    if not EP_URL_PATTERN.match(ep_url.rstrip("/")):
        raise HTTPException(
            status_code=400,
            detail="Invalid enhancement PR URL. "
            "Expected format: https://github.com/openshift/enhancements/pull/<number>",
        )


def _resolve_working_dir(cwd: str) -> str:
    """Resolve and validate the working directory."""
    working_dir = cwd if cwd else os.getcwd()
    if not os.path.isdir(working_dir):
        raise HTTPException(
            status_code=400,
            detail=f"The provided cwd is not a valid directory: {working_dir}",
        )
    return working_dir


HOMEPAGE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OAPE Operator Feature Developer</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #f5f5f5;
         display: flex; justify-content: center; padding: 40px 16px; }
  .card { background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.1);
          padding: 32px; max-width: 720px; width: 100%; }
  h1 { font-size: 1.4rem; margin-bottom: 4px; }
  p.sub { color: #666; font-size: .9rem; margin-bottom: 24px; }
  label { display: block; font-weight: 600; margin-bottom: 6px; font-size: .9rem; }
  input[type=text], select { width: 100%; padding: 10px 12px; border: 1px solid #ccc;
                   border-radius: 6px; font-size: .95rem; }
  input[type=text]:focus, select:focus { outline: none; border-color: #4a90d9; }
  button { margin-top: 16px; padding: 10px 24px; background: #4a90d9; color: #fff;
           border: none; border-radius: 6px; font-size: .95rem; cursor: pointer; }
  button:disabled { background: #aaa; cursor: not-allowed; }
  .spinner { display: inline-block; width: 18px; height: 18px;
             border: 3px solid #ccc; border-top-color: #4a90d9;
             border-radius: 50%; animation: spin .8s linear infinite;
             vertical-align: middle; margin-right: 8px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  #status { margin-top: 20px; font-size: .9rem; color: #555; }
  #conversation { margin-top: 16px; background: #fafafa; border: 1px solid #e0e0e0;
                  border-radius: 6px; max-height: 500px; overflow-y: auto;
                  display: none; }
  #conversation .msg { padding: 10px 14px; border-bottom: 1px solid #eee;
                       font-size: .85rem; line-height: 1.5; }
  #conversation .msg:last-child { border-bottom: none; }
  .msg-text { color: #333; }
  .msg-text .label { font-weight: 600; color: #4a90d9; margin-right: 6px; }
  .msg-tool { color: #8B6914; background: #FFF8E7; font-family: monospace; font-size: .82rem; }
  .msg-tool-result { color: #555; background: #f5f5f5; font-family: monospace;
                     font-size: .82rem; white-space: pre-wrap; word-break: break-word; }
  .msg-thinking { color: #7B1FA2; background: #F3E5F5; font-style: italic; }
  .msg-result { color: #2E7D32; background: #E8F5E9; font-weight: 600; }
  .msg-other { color: #888; font-size: .8rem; }
  #output { margin-top: 16px; background: #1e1e1e; color: #d4d4d4;
            padding: 16px; border-radius: 6px; font-family: monospace;
            font-size: .85rem; white-space: pre-wrap; word-break: break-word;
            max-height: 500px; overflow-y: auto; display: none; }
  .error { color: #c0392b; }
  .content-preview { max-height: 120px; overflow: hidden; position: relative; }
  .content-preview.expanded { max-height: none; }
  .toggle-expand { color: #4a90d9; cursor: pointer; font-size: .8rem;
                   display: inline-block; margin-top: 4px; }
</style>
</head>
<body>
<div class="card">
  <h1>OAPE Operator Feature Developer</h1>
  <p class="sub">Generate controller code from an OpenShift Enhancement Proposal</p>
  <form id="epForm">
    <label for="command">Command</label>
    <select id="command" name="command">
      <option value="api-implement" selected>api-implement</option>
    </select>
    <label for="ep_url" style="margin-top:14px">Enhancement Proposal PR URL</label>
    <input type="text" id="ep_url" name="ep_url"
           placeholder="https://github.com/openshift/enhancements/pull/1234" required>
    <label for="cwd" style="margin-top:14px">Working Directory <span style="color:#999">(optional)</span></label>
    <input type="text" id="cwd" name="cwd" placeholder="/path/to/operator-repo">
    <button type="submit" id="submitBtn">Generate</button>
  </form>
  <div id="status"></div>
  <div id="conversation"></div>
  <pre id="output"></pre>
</div>
<script>
const form     = document.getElementById('epForm');
const btn      = document.getElementById('submitBtn');
const statusEl = document.getElementById('status');
const convEl   = document.getElementById('conversation');
const outputEl = document.getElementById('output');

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

function truncate(str, maxLen) {
  if (!str) return '';
  return str.length <= maxLen ? str : str.substring(0, maxLen) + '\\u2026';
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const epUrl   = document.getElementById('ep_url').value.trim();
  const cwd     = document.getElementById('cwd').value.trim();
  const command = document.getElementById('command').value;
  if (!epUrl) return;

  btn.disabled = true;
  outputEl.style.display = 'none';
  outputEl.textContent = '';
  convEl.style.display = 'none';
  convEl.innerHTML = '';
  statusEl.innerHTML = '<span class="spinner"></span> Submitting job\\u2026';

  try {
    const body = new URLSearchParams({ep_url: epUrl, command: command});
    if (cwd) body.append('cwd', cwd);
    const res = await fetch('/submit', {method: 'POST', body});
    if (!res.ok) { throw new Error((await res.json()).detail || res.statusText); }
    const {job_id} = await res.json();
    statusEl.innerHTML = '<span class="spinner"></span> Connecting to agent stream\\u2026';
    streamJob(job_id);
  } catch (err) {
    statusEl.innerHTML = '<span class="error">Error: ' + escapeHtml(err.message) + '</span>';
    btn.disabled = false;
  }
});

function streamJob(jobId) {
  const es = new EventSource('/stream/' + jobId);

  es.addEventListener('message', (e) => {
    const msg = JSON.parse(e.data);
    convEl.style.display = 'block';
    appendMessage(msg);
    updateStatus(msg);
  });

  es.addEventListener('complete', (e) => {
    const result = JSON.parse(e.data);
    es.close();
    btn.disabled = false;

    if (result.status === 'success') {
      statusEl.innerHTML = 'Done! Cost: $' + (result.cost_usd || 0).toFixed(4);
      if (result.output) {
        outputEl.textContent = result.output;
        outputEl.style.display = 'block';
      }
    } else {
      statusEl.innerHTML = '<span class="error">Failed: '
        + escapeHtml(result.error || 'unknown error') + '</span>';
    }
  });

  es.addEventListener('error', () => {
    es.close();
    btn.disabled = false;
    if (statusEl.querySelector('.spinner')) {
      statusEl.innerHTML = '<span class="error">Stream connection lost</span>';
    }
  });
}

function appendMessage(msg) {
  const div = document.createElement('div');
  div.className = 'msg';

  if (msg.type === 'assistant' && msg.block_type === 'text') {
    div.classList.add('msg-text');
    div.innerHTML = '<span class="label">Assistant</span>'
      + escapeHtml(msg.content);
  } else if (msg.type === 'assistant' && msg.block_type === 'tool_use') {
    div.classList.add('msg-tool');
    const inputPreview = truncate(JSON.stringify(msg.tool_input), 200);
    div.innerHTML = '&#9881; <b>' + escapeHtml(msg.tool_name) + '</b> '
      + '<span style="color:#aaa">' + escapeHtml(inputPreview) + '</span>';
  } else if (msg.type === 'assistant' && msg.block_type === 'tool_result') {
    div.classList.add('msg-tool-result');
    const content = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content);
    const preview = truncate(content, 500);
    const prefix = msg.is_error ? '&#10060; ' : '&#10004; ';
    div.innerHTML = prefix + escapeHtml(preview);
  } else if (msg.type === 'assistant' && msg.block_type === 'thinking') {
    div.classList.add('msg-thinking');
    div.textContent = 'Thinking\\u2026';
  } else if (msg.type === 'result') {
    div.classList.add('msg-result');
    div.textContent = 'Result received (cost: $'
      + (msg.cost_usd || 0).toFixed(4) + ')';
  } else {
    div.classList.add('msg-other');
    div.textContent = '[' + (msg.type || 'event') + '] '
      + truncate(msg.content || '', 100);
  }

  convEl.appendChild(div);
  convEl.scrollTop = convEl.scrollHeight;
}

function updateStatus(msg) {
  if (msg.type === 'assistant' && msg.block_type === 'text') {
    statusEl.innerHTML = '<span class="spinner"></span> '
      + escapeHtml(truncate(msg.content, 80));
  } else if (msg.type === 'assistant' && msg.block_type === 'tool_use') {
    statusEl.innerHTML = '<span class="spinner"></span> Running: '
      + escapeHtml(msg.tool_name) + '\\u2026';
  } else if (msg.type === 'assistant' && msg.block_type === 'thinking') {
    statusEl.innerHTML = '<span class="spinner"></span> Agent is thinking\\u2026';
  } else if (msg.type === 'result') {
    statusEl.innerHTML = '<span class="spinner"></span> Finalizing\\u2026';
  }
}
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def homepage():
    """Serve the submission form."""
    return HOMEPAGE_HTML


@app.post("/submit")
async def submit_job(
    ep_url: str = Form(...),
    command: str = Form(default="api-implement"),
    cwd: str = Form(default=""),
):
    """Validate inputs, create a background job, and return its ID."""
    _validate_ep_url(ep_url)
    if command not in SUPPORTED_COMMANDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported command: {command}. "
            f"Supported: {', '.join(SUPPORTED_COMMANDS)}",
        )
    working_dir = _resolve_working_dir(cwd)

    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {
        "status": "running",
        "ep_url": ep_url,
        "cwd": working_dir,
        "conversation": [],
        "message_event": asyncio.Condition(),
        "output": "",
        "cost_usd": 0.0,
        "error": None,
    }
    asyncio.create_task(_run_job(job_id, command, ep_url, working_dir))
    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def job_status(job_id: str):
    """Return the current status of a job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    return {
        "status": job["status"],
        "ep_url": job["ep_url"],
        "cwd": job["cwd"],
        "output": job.get("output", ""),
        "cost_usd": job.get("cost_usd", 0.0),
        "error": job.get("error"),
        "message_count": len(job.get("conversation", [])),
    }


@app.get("/stream/{job_id}")
async def stream_job(job_id: str):
    """Stream job conversation messages via Server-Sent Events."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        cursor = 0
        condition = jobs[job_id]["message_event"]

        while True:
            # Send any new messages since the cursor
            conversation = jobs[job_id]["conversation"]
            while cursor < len(conversation):
                yield {
                    "event": "message",
                    "data": json.dumps(conversation[cursor], default=str),
                }
                cursor += 1

            # Check if the job is complete
            status = jobs[job_id]["status"]
            if status != "running":
                yield {
                    "event": "complete",
                    "data": json.dumps({
                        "status": status,
                        "output": jobs[job_id].get("output", ""),
                        "cost_usd": jobs[job_id].get("cost_usd", 0.0),
                        "error": jobs[job_id].get("error"),
                    }),
                }
                return

            # Wait for new messages or send keepalive on timeout
            async with condition:
                try:
                    await asyncio.wait_for(condition.wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield {"event": "keepalive", "data": ""}

    return EventSourceResponse(event_generator())


async def _run_job(job_id: str, command: str, ep_url: str, working_dir: str):
    """Run the Claude agent in the background and stream messages to the job store."""
    condition = jobs[job_id]["message_event"]

    loop = asyncio.get_running_loop()

    def on_message(msg: dict) -> None:
        jobs[job_id]["conversation"].append(msg)
        loop.create_task(_notify(condition))

    result = await run_agent(command, ep_url, working_dir, on_message=on_message)
    if result.success:
        jobs[job_id]["status"] = "success"
        jobs[job_id]["output"] = result.output
        jobs[job_id]["cost_usd"] = result.cost_usd
    else:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = result.error

    # Final notification so SSE clients see the status change
    async with condition:
        condition.notify_all()


async def _notify(condition: asyncio.Condition) -> None:
    """Notify all waiters on the condition."""
    async with condition:
        condition.notify_all()


@app.get("/api/v1/oape-api-implement")
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
    """Generate controller/reconciler code from an enhancement proposal (synchronous)."""
    _validate_ep_url(ep_url)
    working_dir = _resolve_working_dir(cwd)

    result = await run_agent("api-implement", ep_url, working_dir)
    if not result.success:
        raise HTTPException(
            status_code=500, detail=f"Agent execution failed: {result.error}"
        )

    return {
        "status": "success",
        "ep_url": ep_url,
        "cwd": working_dir,
        "output": result.output,
        "cost_usd": result.cost_usd,
    }
