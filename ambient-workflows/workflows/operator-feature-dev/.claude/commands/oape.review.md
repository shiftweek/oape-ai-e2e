# /oape.review - Production-grade code review with auto-fix

## Purpose

Perform a "Principal Engineer" level code review that validates the generated
code against the Enhancement Proposal requirements, OpenShift safety standards,
and build consistency. Automatically applies fixes for issues found.

This command is reusable across all 3 PR phases (API types, controller, E2E
tests). It detects which phase is active from the git diff context.

## Arguments

- `$ARGUMENTS`: `<base-branch>` — the git ref to diff against (e.g., `main`, `origin/main`)
  Defaults to `origin/main` if not provided.

## Process

### Step 1: Determine Base Ref

```bash
BASE_REF="${1:-origin/main}"
echo "Base ref: $BASE_REF"
```

### Step 2: Fetch Context

1. **Enhancement Proposal**: Read from `artifacts/operator-feature-dev/init-summary.md`
   or `artifacts/operator-feature-dev/api/generation-summary.md` for EP context.
   Use the EP requirements as the primary validation source (replacing Jira
   Acceptance Criteria from the OAPE review).

2. **Git Diff**: Get the code changes:

   ```bash
   git diff ${BASE_REF}...HEAD --stat -p
   ```

3. **File List**: Get changed files:

   ```bash
   git diff ${BASE_REF}...HEAD --name-only
   ```

4. **Detect Phase**: Determine which PR phase is active based on changed files:
   - API types files (`*_types.go`, `types_*.go`, `*.testsuite.yaml`) → API phase
   - Controller files (`*controller*.go`, `*reconcile*.go`) → Controller phase
   - E2E test files (`*e2e*`, `test-cases.md`) → E2E phase
   - Mixed → review all categories

### Step 3: Analyze Code Changes

Apply **all** modules. Modules A–D are **mandatory** — every check must be
evaluated. Module E is adaptive based on the PR content.

#### Module A: Golang (Logic & Safety)

**Logic Verification (The "Mental Sandbox")**:

- **Intent Match**: Does the code match the EP requirements? Quote the EP
  section that justifies the change.
- **Execution Trace**: Mentally simulate the function.
  - *Happy Path*: Does it succeed as expected?
  - *Error Path*: If the API fails, does it retry or return an error?
- **Edge Cases**:
  - **Nil/Empty**: Does it handle `nil` pointers or empty slices?
  - **State**: Does it handle resources that are `Deleting` or `Pending`?

**Safety & Patterns**:

- **Context**: REJECT `context.TODO()` in production paths. Must use `context.WithTimeout`.
- **Concurrency**: `go func` must be tracked (WaitGroup/ErrGroup). No race conditions.
- **Errors**: Must use `fmt.Errorf("... %w", err)`. No capitalized error strings.
- **Complexity**: Flag functions > 50 lines or > 3 nesting levels.

**Idiomatic Clean Code**:

- **Slices/Maps**: Pre-allocate with `make` if length is known.
- **Interfaces**: Reject "Interface Pollution" (interfaces before multiple implementations).
- **Naming**: Follow Go conventions (`url` not `URL` in mixed-case, `id` not `ID` for local vars).
- **Receiver Types**: Check consistency in pointer vs value receivers.

**Scheme Registration** *(Severity: CRITICAL)*:

- For every `client.Get/List/Create/Update/Delete` call, identify the GVK.
- Read `main.go` or `*scheme*.go` for `AddToScheme` calls.
- Every external type used in client calls must have `AddToScheme` registration.

**Namespace Hardcoding** *(Severity: WARNING)*:

- Scan for string literals matching `"openshift-*"`, `"kube-*"`, `"default"` as namespace values.
- Should use constants, env vars, or config structs.
- Ignore test files and log messages.

**Status Handling (Infinite Requeue Prevention)** *(Severity: WARNING)*:

- Flag patterns where terminal/validation errors cause `return ctrl.Result{}, err`.
- Terminal failures should set Degraded condition and return `ctrl.Result{}, nil`.

**Event Recording** *(Severity: INFO)*:

- Check if reconciler embeds `record.EventRecorder`.
- Flag significant state transitions without `recorder.Event()` calls.

#### Module B: Bash (Scripts)

- **Safety**: Must start with `set -euo pipefail`.
- **Quoting**: Variables in `oc`/`kubectl` commands MUST be quoted.
- **Tmp Files**: Must use `mktemp`, never hardcoded `/tmp/data`.

#### Module C: Operator Metadata (OLM)

- **RBAC**: If new K8s APIs are used, check if `config/rbac/role.yaml` is updated.
- **RBAC Three-Way Consistency** *(Severity: CRITICAL)*:
  Cross-reference three sources:
  1. Kubebuilder markers in Go files
  2. `config/rbac/role.yaml`
  3. CSV permissions in `bundle/manifests/`
  All must declare the same groups, resources, and verbs.
- **Finalizers**: If logic deletes resources, ensure finalizers are handled.

#### Module D: Build Consistency

- **Generation Drift**:
  - IF `types.go` modified AND `zz_generated.deepcopy.go` NOT in file list → **CRITICAL FAIL**
  - IF `types.go` modified AND `config/crd/bases/` NOT in file list → **CRITICAL FAIL**
- **Dependency Completeness** *(Severity: WARNING)*:
  - New imports must exist in `go.mod`
  - If `vendor/` exists and `go.mod` changed but `vendor/modules.txt` didn't, flag it

#### Module E: Context-Adaptive Review

After mandatory checks, perform an open-ended review tailored to this PR:

- **OwnerReferences**: If creating child resources, verify owner refs are set *(CRITICAL)*
- **Proxy/Disconnected**: If making HTTP calls, verify proxy env vars are respected *(WARNING)*
- **API Deprecation**: Flag deprecated API versions *(WARNING)*
- **Watch Predicates**: Check if filtering predicates are used to avoid excessive reconciliation *(INFO)*
- **Resource Requests/Limits**: If creating Pod specs, check for resource limits *(INFO)*
- **Leader Election Safety**: If modifying cluster-scoped resources, verify leader election *(WARNING)*

Use judgment to flag additional concerns not covered by Modules A–D.

### Step 4: Generate Report

Generate a structured JSON report:

```json
{
  "summary": {
    "verdict": "Approved | Changes Requested",
    "rating": "1-10",
    "simplicity_score": "1-10"
  },
  "logic_verification": {
    "ep_intent_met": true,
    "missing_edge_cases": ["description of gaps"]
  },
  "issues": [
    {
      "severity": "CRITICAL | WARNING | INFO",
      "module": "Logic | Bash | OLM | Build | Adaptive",
      "file": "path/to/file.go",
      "line": 45,
      "description": "What's wrong",
      "fix_prompt": "How to fix it"
    }
  ]
}
```

### Step 5: Apply Fixes Automatically

If the `issues` array is non-empty, automatically apply the suggested fixes:

1. Sort issues by severity (CRITICAL first)
2. For each issue with a `fix_prompt`, apply the fix
3. Run `make generate && make build` to verify fixes compile
4. Report which fixes were applied and which need manual attention

Skip this step when verdict is "Approved" with no issues.

### Step 6: Write Verdict

Detect the current phase and write the verdict to the appropriate artifact:

- API phase → `artifacts/operator-feature-dev/api/review-verdict.md`
- Controller phase → `artifacts/operator-feature-dev/impl/review-verdict.md`
- E2E phase → `artifacts/operator-feature-dev/e2e/review-verdict.md`

## Critical Failure Conditions

1. Not inside a git repository
2. Base ref does not exist
3. No changes detected between base ref and HEAD

## Behavioral Rules

1. Every check in Modules A–D must be evaluated on every review
2. Module E is adaptive — extend based on what the PR actually does
3. Report findings with file path and line number
4. Auto-apply fixes when possible, report when manual intervention needed
