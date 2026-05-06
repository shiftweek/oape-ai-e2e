# /oape.e2e-generate - Generate E2E test artifacts from git diff

## Purpose

Analyze the current OpenShift operator repository and generate all E2E test
artifacts based on the diff between a base branch and HEAD. Produces test cases,
execution steps, E2E test code, and recommendations.

## Arguments

- `$ARGUMENTS`: `<base-branch>` — the git branch to diff against (e.g., `main`, `origin/main`)

## Prerequisites

- Must be run from within an OpenShift operator repository
- `git`, `go` installed
- Changes must exist between `<base-branch>` and HEAD

## Process

### Phase 0: Prechecks

All prechecks must pass before proceeding. If ANY fails, STOP immediately.

#### Precheck 1 — Validate Arguments

```bash
BASE_BRANCH="$1"

if [ -z "$BASE_BRANCH" ]; then
  echo "PRECHECK FAILED: No base branch provided."
  echo "Usage: /oape.e2e-generate <base-branch>"
  exit 1
fi

echo "Base branch: $BASE_BRANCH"
```

#### Precheck 2 — Verify Required Tools

```bash
MISSING_TOOLS=""

if ! command -v git &> /dev/null; then
  MISSING_TOOLS="$MISSING_TOOLS git"
fi

if ! command -v go &> /dev/null; then
  MISSING_TOOLS="$MISSING_TOOLS go"
fi

if [ -n "$MISSING_TOOLS" ]; then
  echo "PRECHECK FAILED: Missing required tools:$MISSING_TOOLS"
  exit 1
fi

if ! command -v oc &> /dev/null; then
  echo "WARNING: oc not found. Generated execution steps require oc to run."
fi

echo "Required tools available."
```

#### Precheck 3 — Verify Repository

```bash
if ! git rev-parse --is-inside-work-tree &> /dev/null 2>&1; then
  echo "PRECHECK FAILED: Not inside a git repository."
  exit 1
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
echo "Repository root: $REPO_ROOT"

if [ ! -f "$REPO_ROOT/go.mod" ]; then
  echo "PRECHECK FAILED: No go.mod found at repository root."
  exit 1
fi

GO_MODULE=$(head -1 "$REPO_ROOT/go.mod" | awk '{print $2}')
REPO_NAME=$(basename "$GO_MODULE")
echo "Go module: $GO_MODULE"
echo "Repo name: $REPO_NAME"

# Detect framework
HAS_CR=false
HAS_LIBGO=false
grep -q "sigs.k8s.io/controller-runtime" "$REPO_ROOT/go.mod" && HAS_CR=true
grep -q "github.com/openshift/library-go" "$REPO_ROOT/go.mod" && HAS_LIBGO=true

if [ "$HAS_CR" = true ]; then
  FRAMEWORK="controller-runtime"
elif [ "$HAS_LIBGO" = true ]; then
  FRAMEWORK="library-go"
else
  echo "PRECHECK FAILED: Cannot determine operator framework."
  exit 1
fi

echo "Detected framework: $FRAMEWORK"
```

#### Precheck 4 — Validate Git Diff is Non-Empty

```bash
if ! git rev-parse --verify "$BASE_BRANCH" &> /dev/null 2>&1; then
  echo "PRECHECK FAILED: Base branch '$BASE_BRANCH' does not exist."
  git branch -a | head -20
  exit 1
fi

DIFF_STAT=$(git diff "$BASE_BRANCH"...HEAD --stat 2>/dev/null)

if [ -z "$DIFF_STAT" ]; then
  echo "PRECHECK FAILED: No changes detected between '$BASE_BRANCH' and HEAD."
  exit 1
fi

echo "Changes detected:"
echo "$DIFF_STAT"
```

**If ALL prechecks passed, proceed to Phase 1.**

---

### Phase 1: Framework Detection and Repository Discovery

All subsequent phases use discovered information — never hardcoded values.

#### Step 1.1: Discover API Types

```bash
find "$REPO_ROOT" -type f \( -name '*_types.go' -o -name 'types_*.go' \) \
  -not -path '*/vendor/*' -not -path '*/_output/*' -not -path '*/zz_generated*' | head -40
```

For each types file, extract: API group and version, Kind names, spec/status
fields, condition types, scope (cluster/namespaced).

If no types files found in repo, check `go.mod` for `github.com/openshift/api`
dependency — types may be external.

#### Step 1.2: Discover CRDs

```bash
find "$REPO_ROOT" -type f -name '*.yaml' \( -path '*/crd/*' -o -path '*/crds/*' -o -path '*/manifests/*' \) \
  -not -path '*/vendor/*' | head -30
```

Extract: Kind, group, plural resource name, scope, served versions.

#### Step 1.3: Discover Existing E2E Test Patterns

```bash
# Go-based e2e tests
find "$REPO_ROOT" -type f -name '*_test.go' -path '*/e2e/*' -not -path '*/vendor/*' | head -20

# Bash-based e2e tests
find "$REPO_ROOT" -type f -name '*.sh' \( -path '*/e2e/*' -o -path '*/hack/e2e*' \) -not -path '*/vendor/*' | head -10
```

If Go tests found with Ginkgo imports: read 1-2 files to understand package
name, import paths, client variables, helper utilities, assertion patterns.

If bash scripts found: read script to understand test structure.

If no existing tests: default to Ginkgo for controller-runtime, bash for
library-go.

#### Step 1.4: Discover Install Mechanism

```bash
# OLM manifests
find "$REPO_ROOT" -type f -name '*.yaml' \
  \( -path '*/config/manifests/*' -o -path '*/bundle/*' \) \
  -not -path '*/vendor/*' | head -20

# Deployment manifests
find "$REPO_ROOT" -type f -name '*.yaml' \
  \( -path '*/config/default/*' -o -path '*/deploy/*' \) \
  -not -path '*/vendor/*' | head -20
```

Extract: package name, channel, CSV name, install namespace.

#### Step 1.5: Discover Sample CRs

```bash
find "$REPO_ROOT" -type f -name '*.yaml' \
  \( -path '*/config/samples/*' -o -path '*/examples/*' \) \
  -not -path '*/vendor/*' | head -20
```

#### Step 1.6: Discover Operator Namespace

Search order: E2E constants file → CSV manifest → namespace YAML → placeholder.

#### Step 1.7: Discover Controllers

```bash
find "$REPO_ROOT" -type f -name '*.go' \
  \( -name '*controller*' -o -name '*reconcile*' -o -name 'starter.go' \) \
  -not -path '*/vendor/*' -not -name '*_test.go' | head -20
```

#### Step 1.8: Build Repo Profile

```thinking
Summarize: framework, Go module, API types, CRDs, E2E pattern, install
mechanism, samples, operator namespace, controllers, managed workloads.
This profile drives all subsequent generation. No hardcoded values.
```

---

### Phase 2: Analyze Git Diff

```bash
git diff "$BASE_BRANCH"...HEAD --stat
git diff "$BASE_BRANCH"...HEAD -p
git log "$BASE_BRANCH"...HEAD --oneline
```

Categorize each changed file:

| File Pattern | Category | Test Focus |
| --- | --- | --- |
| `api/**/*_types.go`, `types_*.go` | API Types | New/changed fields, validation |
| `config/crd/**/*.yaml` | CRD Changes | Schema updates |
| `*controller*.go`, `*reconcile*.go` | Controller | Reconciliation logic |
| `config/rbac/*.yaml` | RBAC | Permission changes |
| `config/samples/*.yaml` | Samples | Example CR usage |
| `test/e2e/**` | E2E Tests | Existing patterns (don't duplicate) |

Map each meaningful change to a specific test scenario.

---

### Phase 3: Generate test-cases.md

Write `artifacts/operator-feature-dev/e2e/test-cases.md` with:

- Operator information (repo, framework, API group, managed CRDs, namespace)
- Prerequisites (cluster access, CLI tools, env vars)
- Installation steps (OLM or manual, using discovered values)
- CR deployment steps (using discovered sample CRs)
- Test cases grouped by diff category
- Verification commands
- Cleanup in reverse dependency order

---

### Phase 4: Generate execution-steps.md

Write `artifacts/operator-feature-dev/e2e/execution-steps.md` with step-by-step
`oc` commands for: prerequisites, environment setup, operator install, CR
deployment, verification, diff-specific tests, cleanup.

---

### Phase 5: Generate E2E Test Code

#### Path A — Ginkgo (controller-runtime repos)

Generate `e2e_test.go`:

- Match existing e2e package name, imports, client variables, helpers
- `Describe`/`Context`/`It` structure with `By("...")` steps
- No suite logic (no BeforeSuite, TestE2E, client setup)
- Each `It` block prefixed with `// Diff-suggested: <reason>`
- Cover both important general scenarios and diff-specific tests

#### Path B — Bash (library-go repos)

Generate `e2e_test.sh`:

- `#!/usr/bin/env bash` with `set -euo pipefail`
- Configuration variables using discovered values
- `test_<scenario>()` functions for each test case
- `trap cleanup EXIT`
- Each function prefixed with `# Diff-suggested: <reason>`

---

### Phase 6: Generate e2e-suggestions.md

Write `artifacts/operator-feature-dev/e2e/e2e-suggestions.md` with:

- Detected operator structure summary
- Changes detected in diff
- Highly recommended scenarios per change
- Optional/nice-to-have scenarios
- Gaps that are hard to test automatically

---

### Phase 7: Output Summary

Write `artifacts/operator-feature-dev/e2e/generation-summary.md`:

```text
=== E2E Test Generation Summary ===

Repository: <go-module>
Framework: <controller-runtime|library-go>
Base Branch: <base-branch>
Changes Analyzed: <N files changed>

Generated Files:
  - artifacts/operator-feature-dev/e2e/test-cases.md
  - artifacts/operator-feature-dev/e2e/execution-steps.md
  - artifacts/operator-feature-dev/e2e/e2e_test.go (or e2e_test.sh)
  - artifacts/operator-feature-dev/e2e/e2e-suggestions.md

Next Steps:
  1. Review generated test cases and suggestions
  2. Copy e2e test code into the repo's test/e2e/ directory
  3. Adjust placeholder values if any remain
  4. Run tests against a live cluster
```

## Behavioral Rules

1. **Never hardcode**: All operator-specific values must be discovered from the repo
2. **Match existing style**: Generated code must match existing e2e test conventions
3. **Diff-driven focus**: Only generate tests for code that changed
4. **Fail on ambiguity**: If repo structure is ambiguous, STOP and ask
5. **Minimal placeholders**: Replace as many as possible with discovered values
6. **No duplicate suite logic**: For Ginkgo, only generate test blocks
7. **Correct cleanup order**: Always cleanup in reverse dependency order
