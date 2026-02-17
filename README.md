# OAPE AI E2E

AI-driven end-to-end feature development tools for OpenShift operators.

## Overview

OAPE (OpenShift AI-Powered Engineering) provides AI-driven tools that take an Enhancement Proposal (EP) and generate:
1. **API type definitions** (Go structs)
2. **Integration tests** for API types
3. **Controller/reconciler** implementation code
4. **E2E test artifacts**

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Two Usage Modes                                │
├─────────────────────────────────┬───────────────────────────────────────┤
│       IDE Plugin Mode           │         Server Mode (API)             │
│  (Claude Code / Cursor)         │      (Direct Vertex AI)               │
├─────────────────────────────────┼───────────────────────────────────────┤
│  /oape:api-generate <EP-URL>    │  POST /api/v1/run                     │
│  /oape:api-implement <EP-URL>   │  { command, prompt, working_dir }     │
│  /oape:e2e-generate <branch>    │                                       │
└─────────────────────────────────┴───────────────────────────────────────┘
                    │                              │
                    └──────────────┬───────────────┘
                                   ▼
         ┌─────────────────────────────────────────────────┐
         │  plugins/oape/commands/*.md  (Command Logic)    │
         │  plugins/oape/skills/*.md    (Reusable Skills)  │
         └─────────────────────────────────────────────────┘
```

## Quick Start

### Option 1: IDE Plugin (Claude Code / Cursor)

```bash
# Clone and symlink for Cursor
git clone git@github.com:shiftweek/oape-ai-e2e.git
ln -s $(pwd)/oape-ai-e2e ~/.cursor/commands/oape-ai-e2e

# Use commands directly
/oape:init cert-manager-operator
/oape:api-generate https://github.com/openshift/enhancements/pull/1234
```

### Option 2: Server Mode (Direct API)

```bash
cd server
pip install -r requirements.txt

# Set GCP credentials
export ANTHROPIC_VERTEX_PROJECT_ID="your-project"
export CLOUD_ML_REGION="us-east5"
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/gcloud/application_default_credentials.json"

# Run server
uvicorn main:app --reload --port 8000

# Access web UI at http://localhost:8000
# Or use API: POST /api/v1/run
```

## Available Commands

| Command | Description |
|---------|-------------|
| `/oape:init <repo-name>` | Clone an allowed operator repository |
| `/oape:api-generate <EP-URL>` | Generate API types from Enhancement Proposal |
| `/oape:api-generate-tests <path>` | Generate integration tests for API types |
| `/oape:api-implement <EP-URL>` | Generate controller code from Enhancement Proposal |
| `/oape:e2e-generate <base-branch>` | Generate e2e test artifacts from git diff |
| `/oape:review <ticket-id>` | Code review against Jira requirements |
| `/oape:implement-review-fixes <report>` | Apply fixes from review report |

## Typical Workflow

```bash
# 1. Clone the operator repository
/oape:init cert-manager-operator

# 2. Generate API types from enhancement proposal
/oape:api-generate https://github.com/openshift/enhancements/pull/1234

# 3. Generate integration tests for the new types
/oape:api-generate-tests api/v1alpha1/

# 4. Generate controller implementation
/oape:api-implement https://github.com/openshift/enhancements/pull/1234

# 5. Build and verify
make generate && make manifests && make build && make test

# 6. Generate e2e tests for your changes
/oape:e2e-generate main
```

## Project Structure

```
oape-ai-e2e/
├── AGENTS.md               # AI agent instructions (system prompt base)
├── team-repos.csv          # Allowed operator repositories
├── plugins/oape/           # Command and skill definitions
│   ├── commands/           # Slash command implementations
│   │   ├── init.md
│   │   ├── api-generate.md
│   │   ├── api-implement.md
│   │   └── ...
│   ├── skills/             # Reusable knowledge modules
│   │   ├── effective-go/
│   │   └── e2e-test-generator/
│   └── e2e-test-generator/ # Fixtures and examples
├── server/                 # FastAPI server (Vertex AI)
│   ├── main.py             # API endpoints
│   ├── vertex_client.py    # Direct Vertex AI client
│   ├── context_loader.py   # Loads MD files as context
│   ├── tools/              # Tool implementations
│   └── README.md           # Server documentation
├── deploy/                 # Kubernetes deployment
│   └── deployment.yaml
└── Dockerfile
```

## Supported Repositories

The allowed repositories are defined in [`team-repos.csv`](team-repos.csv):

| Product | Role | Repository |
|---------|------|------------|
| cert-manager Operator | upstream operand | openshift/jetstack-cert-manager |
| cert-manager Operator | downstream operator | openshift/cert-manager-operator |
| cert-manager Operator | istio integration | openshift/cert-manager-istio-csr |
| External Secrets Operator | upstream fork | openshift/external-secrets-operator |

## Framework Detection

Commands auto-detect the operator framework:

| Framework | Detection | Code Pattern |
|-----------|-----------|--------------|
| **controller-runtime** | `sigs.k8s.io/controller-runtime` in go.mod | `Reconcile(ctx, req) (Result, error)` |
| **library-go** | `github.com/openshift/library-go` in go.mod | `sync(ctx, syncCtx) error` |

## Server API

See [`server/README.md`](server/README.md) for full API documentation.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Web UI |
| `/submit` | POST | Submit async job |
| `/stream/{job_id}` | GET | SSE stream |
| `/api/v1/run` | POST | Run command (sync) |
| `/api/v1/commands` | GET | List commands |

## Docker Deployment

```bash
# Build
docker build -t oape-server .

# Run locally
docker run -p 8000:8000 \
  -e ANTHROPIC_VERTEX_PROJECT_ID="your-project" \
  -e CLOUD_ML_REGION="us-east5" \
  -v $HOME/.config/gcloud:/secrets/gcloud:ro \
  -e GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcloud/application_default_credentials.json \
  oape-server
```

## Kubernetes Deployment

```bash
# Update secrets in deploy/deployment.yaml first
kubectl apply -f deploy/deployment.yaml
```

## Conventions Enforced

- [OpenShift API Conventions](https://github.com/openshift/enhancements/blob/master/dev-guide/api-conventions.md)
- [Kubernetes API Conventions](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md)
- [Kubebuilder Controller Patterns](https://book.kubebuilder.io/)
- [Effective Go](https://go.dev/doc/effective_go)

## Prerequisites

- **gh** (GitHub CLI) — installed and authenticated
- **go** — Go toolchain
- **git** — Git
- **make** — Make
- For server mode: Python 3.11+, GCP credentials with Vertex AI access

## License

See [LICENSE](LICENSE).
