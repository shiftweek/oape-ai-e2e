"""
FastAPI server that exposes OAPE Claude Code skills via the Claude Agent SDK.

Usage:
    uvicorn server:app --reload

Endpoints:
    GET  /                                    - Homepage with submission form
    POST /submit                              - Submit a job (returns job_id)
    GET  /status/{job_id}                     - Poll job status
    GET  /api/v1/oape-api-implement?ep_url=.. - Synchronous API-implement endpoint
"""

import asyncio
import os
import re
import uuid

from fastapi import FastAPI, HTTPException, Query, Form
from fastapi.responses import HTMLResponse

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
          padding: 32px; max-width: 640px; width: 100%; }
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
  #output { margin-top: 16px; background: #1e1e1e; color: #d4d4d4;
            padding: 16px; border-radius: 6px; font-family: monospace;
            font-size: .85rem; white-space: pre-wrap; word-break: break-word;
            max-height: 500px; overflow-y: auto; display: none; }
  .error { color: #c0392b; }
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
  <pre id="output"></pre>
</div>
<script>
const form     = document.getElementById('epForm');
const btn      = document.getElementById('submitBtn');
const statusEl = document.getElementById('status');
const outputEl = document.getElementById('output');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const epUrl   = document.getElementById('ep_url').value.trim();
  const cwd     = document.getElementById('cwd').value.trim();
  const command = document.getElementById('command').value;
  if (!epUrl) return;

  btn.disabled = true;
  outputEl.style.display = 'none';
  outputEl.textContent = '';
  statusEl.innerHTML = '<span class="spinner"></span> Submitting job\u2026';

  try {
    const body = new URLSearchParams({ep_url: epUrl, command: command});
    if (cwd) body.append('cwd', cwd);
    const res = await fetch('/submit', {method: 'POST', body});
    if (!res.ok) { throw new Error((await res.json()).detail || res.statusText); }
    const {job_id} = await res.json();
    statusEl.innerHTML = '<span class="spinner"></span> Running agent\u2026 (polling for results)';
    pollJob(job_id);
  } catch (err) {
    statusEl.innerHTML = '<span class="error">Error: ' + err.message + '</span>';
    btn.disabled = false;
  }
});

function pollJob(jobId) {
  const iv = setInterval(async () => {
    try {
      const res = await fetch('/status/' + jobId);
      if (!res.ok) { throw new Error((await res.json()).detail || res.statusText); }
      const data = await res.json();
      if (data.status === 'running') {
        statusEl.innerHTML = '<span class="spinner"></span> Agent is working\u2026';
        return;
      }
      clearInterval(iv);
      btn.disabled = false;
      if (data.status === 'success') {
        statusEl.innerHTML = 'Done! Cost: $' + (data.cost_usd || 0).toFixed(4);
        outputEl.textContent = data.output;
        outputEl.style.display = 'block';
      } else {
        statusEl.innerHTML = '<span class="error">Failed: ' + (data.error || 'unknown error') + '</span>';
      }
    } catch (err) {
      clearInterval(iv);
      btn.disabled = false;
      statusEl.innerHTML = '<span class="error">Polling error: ' + err.message + '</span>';
    }
  }, 3000);
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
    jobs[job_id] = {"status": "running", "ep_url": ep_url, "cwd": working_dir}
    asyncio.create_task(_run_job(job_id, command, ep_url, working_dir))
    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def job_status(job_id: str):
    """Return the current status of a job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


async def _run_job(job_id: str, command: str, ep_url: str, working_dir: str):
    """Run the Claude agent in the background and update the job store."""
    result = await run_agent(command, ep_url, working_dir)
    if result.success:
        jobs[job_id] = {
            "status": "success",
            "ep_url": ep_url,
            "cwd": working_dir,
            "output": result.output,
            "cost_usd": result.cost_usd,
        }
    else:
        jobs[job_id] = {
            "status": "failed",
            "ep_url": ep_url,
            "cwd": working_dir,
            "error": result.error,
        }


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
