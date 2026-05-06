# /oape.api-implement - Generate controller/reconciler implementation

## Purpose

Read an OpenShift Enhancement Proposal PR and/or a design document, extract the
required implementation logic, and generate complete controller/reconciler code
in the correct paths of the current operator repository. Produces
production-ready code with zero TODOs.

## Arguments

- `$ARGUMENTS`: `<ep-url> [--design-doc <gist-url>]`

At least one input source (EP or design document) must be provided. When both
are provided, the design document takes precedence for implementation details.

## Process

### Phase 0: Prechecks

All prechecks must pass before proceeding. If ANY fails, STOP immediately.

#### Precheck 1 -- Parse and Validate Input Arguments

```bash
ARGS="$ARGUMENTS"
ENHANCEMENT_PR=""
DESIGN_DOC_URL=""
ENHANCEMENT_PR_NUMBER=""

if echo "$ARGS" | grep -q '\-\-design-doc'; then
  DESIGN_DOC_URL=$(echo "$ARGS" | sed -n 's/.*--design-doc[[:space:]]\+\([^[:space:]]\+\).*/\1/p')
  ENHANCEMENT_PR=$(echo "$ARGS" | sed 's/--design-doc[[:space:]]\+[^[:space:]]\+//' | xargs)
else
  ENHANCEMENT_PR="$ARGS"
fi

if [ -z "$ENHANCEMENT_PR" ] && [ -z "$DESIGN_DOC_URL" ]; then
  echo "PRECHECK FAILED: No input provided."
  echo "Usage: /oape.api-implement <EP_URL> [--design-doc <GIST_URL>]"
  exit 1
fi

if [ -n "$ENHANCEMENT_PR" ]; then
  if ! echo "$ENHANCEMENT_PR" | grep -qE '^https://github\.com/openshift/enhancements/pull/[0-9]+/?$'; then
    echo "PRECHECK FAILED: Invalid enhancement PR URL."
    echo "Expected: https://github.com/openshift/enhancements/pull/<number>"
    echo "Got: $ENHANCEMENT_PR"
    exit 1
  fi
  ENHANCEMENT_PR_NUMBER=$(echo "$ENHANCEMENT_PR" | grep -oE '[0-9]+$')
  echo "Enhancement PR #$ENHANCEMENT_PR_NUMBER validated."
fi

if [ -n "$DESIGN_DOC_URL" ]; then
  if ! echo "$DESIGN_DOC_URL" | grep -qE '^https://gist\.github(usercontent)?\.com/'; then
    echo "PRECHECK FAILED: Invalid design document URL."
    echo "Expected: https://gist.github.com/[username/]<gist_id>"
    echo "Got: $DESIGN_DOC_URL"
    exit 1
  fi
  echo "Design document URL validated: $DESIGN_DOC_URL"
fi
```

#### Precheck 2 -- Verify Required Tools

```bash
MISSING_TOOLS=""

if ! command -v gh &> /dev/null; then MISSING_TOOLS="$MISSING_TOOLS gh"; fi
if ! command -v go &> /dev/null; then MISSING_TOOLS="$MISSING_TOOLS go"; fi
if ! command -v git &> /dev/null; then MISSING_TOOLS="$MISSING_TOOLS git"; fi
if ! command -v make &> /dev/null; then MISSING_TOOLS="$MISSING_TOOLS make"; fi

if [ -n "$MISSING_TOOLS" ]; then
  echo "PRECHECK FAILED: Missing required tools:$MISSING_TOOLS"
  exit 1
fi

if ! gh auth status &> /dev/null 2>&1; then
  echo "PRECHECK FAILED: GitHub CLI is not authenticated."
  exit 1
fi

echo "All required tools are available and authenticated."
```

#### Precheck 3 -- Verify Current Repository

```bash
if ! git rev-parse --is-inside-work-tree &> /dev/null 2>&1; then
  echo "PRECHECK FAILED: Not inside a git repository."
  exit 1
fi

REPO_ROOT=$(git rev-parse --show-toplevel)

if [ ! -f "$REPO_ROOT/go.mod" ]; then
  echo "PRECHECK FAILED: No go.mod found at repository root."
  exit 1
fi

GO_MODULE=$(head -1 "$REPO_ROOT/go.mod" | awk '{print $2}')
echo "Go module: $GO_MODULE"
```

#### Precheck 4 -- Verify Enhancement PR is Accessible (if provided)

```bash
if [ -n "$ENHANCEMENT_PR_NUMBER" ]; then
  PR_STATE=$(gh pr view "$ENHANCEMENT_PR_NUMBER" --repo openshift/enhancements --json state --jq '.state' 2>/dev/null)

  if [ -z "$PR_STATE" ]; then
    echo "PRECHECK FAILED: Unable to access enhancement PR #$ENHANCEMENT_PR_NUMBER."
    exit 1
  fi

  PR_TITLE=$(gh pr view "$ENHANCEMENT_PR_NUMBER" --repo openshift/enhancements --json title --jq '.title')
  echo "Enhancement PR #$ENHANCEMENT_PR_NUMBER: $PR_TITLE ($PR_STATE)"
fi
```

#### Precheck 5 -- Verify Design Document is Accessible (if provided)

```bash
GIST_ID=""

if [ -n "$DESIGN_DOC_URL" ]; then
  GIST_ID=$(echo "$DESIGN_DOC_URL" | grep -oE '[a-f0-9]{32}' | head -1)

  if [ -z "$GIST_ID" ]; then
    GIST_ID=$(echo "$DESIGN_DOC_URL" | sed 's|.*/||' | sed 's|[?#].*||')
  fi

  if [ -z "$GIST_ID" ]; then
    echo "PRECHECK FAILED: Could not extract gist ID from URL."
    exit 1
  fi

  GIST_INFO=$(gh api "gists/$GIST_ID" --jq '.description // "Untitled"' 2>/dev/null)

  if [ -z "$GIST_INFO" ]; then
    echo "PRECHECK FAILED: Unable to access design document gist."
    exit 1
  fi

  echo "Design document gist verified: $GIST_INFO"
fi
```

#### Precheck 6 -- Verify API Types Exist

```bash
API_TYPES=$(find "$REPO_ROOT" -type f \( -name 'types*.go' -o -name '*_types.go' \) \
  -not -path '*/vendor/*' -not -path '*/_output/*' -not -path '*/zz_generated*' | head -20)

if [ -z "$API_TYPES" ]; then
  echo "PRECHECK FAILED: No API type definitions found."
  echo "Run /oape.api-generate first to create the API types."
  exit 1
fi

echo "Found API types:"
echo "$API_TYPES" | head -10
```

#### Precheck 7 -- Verify Clean Working Tree (Warning)

```bash
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "WARNING: Uncommitted changes detected."
  git status --short
else
  echo "Working tree is clean."
fi
```

**If ALL prechecks passed, proceed to Phase 1.**

---

### Phase 1: Detect Operator Framework

```bash
echo "Detecting operator framework type..."

if [ -f "$REPO_ROOT/PROJECT" ]; then
  echo "Found PROJECT file (operator-sdk/kubebuilder project)"
  cat "$REPO_ROOT/PROJECT"
fi

echo "Checking go.mod for framework dependencies..."

if grep -q "github.com/openshift/library-go" "$REPO_ROOT/go.mod"; then
  echo "Found: github.com/openshift/library-go"
fi

if grep -q "sigs.k8s.io/controller-runtime" "$REPO_ROOT/go.mod"; then
  echo "Found: sigs.k8s.io/controller-runtime"
fi
```

#### Framework Detection Rules

Apply in order:

1. **library-go in go.mod AND `pkg/operator/` exists** ->
   OPERATOR_TYPE = "library-go"
2. **controller-runtime in go.mod** ->
   OPERATOR_TYPE = "controller-runtime"
3. **Neither** -> STOP and ask the user

---

### Phase 2: Refresh Knowledge -- Fetch Operator Conventions

Fetch and read based on OPERATOR_TYPE:

**For controller-runtime:**

1. `https://book.kubebuilder.io/cronjob-tutorial/controller-implementation`
2. `https://pkg.go.dev/sigs.k8s.io/controller-runtime`

**For library-go:**

1. `https://github.com/openshift/library-go/tree/master/pkg/controller`
2. `https://github.com/openshift/library-go/blob/master/pkg/operator/events/recorder.go`

**For all types:**

1. `https://raw.githubusercontent.com/openshift/enhancements/master/dev-guide/operator.md`

---

### Phase 3: Fetch and Parse Input Sources

#### 3.1 Fetch Enhancement Proposal (if provided)

```bash
if [ -n "$ENHANCEMENT_PR_NUMBER" ]; then
  gh pr view "$ENHANCEMENT_PR_NUMBER" --repo openshift/enhancements --json files --jq '.files[].path'
fi
```

Fetch full content:

```bash
gh api "repos/openshift/enhancements/contents/<path>?ref=refs/pull/$ENHANCEMENT_PR_NUMBER/head" --jq '.content' | base64 -d
```

Fallbacks:

```bash
curl -sL "https://raw.githubusercontent.com/openshift/enhancements/refs/pull/$ENHANCEMENT_PR_NUMBER/head/<path>"
gh pr diff "$ENHANCEMENT_PR_NUMBER" --repo openshift/enhancements
```

#### 3.2 Fetch Design Document (if provided)

```bash
if [ -n "$GIST_ID" ]; then
  gh api "gists/$GIST_ID" --jq '.files | to_entries[] | "=== FILE: \(.key) ===\n\(.value.content)\n"'
fi
```

#### 3.3 Extract Structured Requirements

```thinking
Extract structured information using this checklist. Design document takes
precedence for implementation details.

## EXTRACTION CHECKLIST

### A. API Information (Required)
- API Group, Version, Kind, Resource plural, Scope

### B. Spec Fields -> Controller Actions (Required)
For EACH spec field: field name, type, controller action, validation, defaults

### C. Reconciliation Workflow (Required)
Ordered steps for the reconcile loop

### D. Dependent Resources (Required for complete code)
For EACH: resource type, name pattern, namespace, content/spec, lifecycle

### E. External Resources / Integrations (If applicable)
External system, API/SDK, operations, credentials handling

### F. Status Conditions (Required)
Standard OpenShift conditions: Available, Progressing, Degraded
For each: type name, when True/False, reason codes, message templates

### G. Status Fields (Beyond conditions)
For each: field name, what it represents, how to compute it

### H. Events to Record (Required)
For each: event type, reason, when to emit, message template

### I. Error Handling (Required)
Transient errors (retry with backoff), permanent errors (set Degraded)

### J. Cleanup / Deletion (Required if external resources)
What to clean up, order, finalizer name

### K. Watches / Triggers (Required for reactive behavior)
For each: resource type, filter, how to map to primary resource

### L. Feature Gate (If applicable)
Feature gate name, behavior when disabled

### M. RBAC Requirements (Derived)
Based on all above, compute required permissions

If ANY required section (A, B, C, F, I) is missing or ambiguous, STOP and ask.
```

---

### Phase 4: Identify Target Paths for Controller Code

```bash
find "$REPO_ROOT" -type f -name '*controller*.go' -not -path '*/vendor/*' -not -path '*/_output/*' | head -30
find "$REPO_ROOT" -type f -name 'main.go' -not -path '*/vendor/*' | head -10
grep -r "func.*Reconcile\|func.*Sync" "$REPO_ROOT" --include='*.go' -l | grep -v vendor | head -20
grep -r "SetupWithManager\|AddToManager\|NewController\|factory.New" "$REPO_ROOT" --include='*.go' -l | grep -v vendor | head -20
find "$REPO_ROOT" -type f -name 'starter.go' -not -path '*/vendor/*' | head -5
```

#### Layout Patterns by OPERATOR_TYPE

**controller-runtime:**

| Pattern | Controller Location | Registration |
| --- | --- | --- |
| Standard | `controllers/<resource>_controller.go` | `main.go` |
| Internal | `internal/controller/<resource>_controller.go` | `cmd/main.go` |
| Nested | `internal/controller/<resource>/controller.go` | `internal/controller/setup.go` |

**library-go:**

| Pattern | Controller Location | Registration |
| --- | --- | --- |
| Standard | `pkg/operator/<resource>/<resource>_controller.go` | `pkg/operator/starter.go` |
| Flat | `pkg/operator/<resource>_controller.go` | `pkg/operator/operator.go` |

---

### Phase 5: Read Existing Controller Code for Context

```bash
if [ "$OPERATOR_TYPE" = "library-go" ]; then
  SAMPLE_CONTROLLER=$(find "$REPO_ROOT/pkg" -type f -name '*controller*.go' -not -path '*/vendor/*' -not -name '*_test.go' | head -1)
else
  SAMPLE_CONTROLLER=$(find "$REPO_ROOT" -type f -name '*controller*.go' -not -path '*/vendor/*' -not -path '*/_output/*' -not -name '*_test.go' | head -1)
fi
```

```thinking
Read existing controller(s) and extract these EXACT patterns to replicate:
1. Package name
2. Import organization and aliases
3. Struct fields
4. Constructor pattern
5. Reconcile/Sync signature
6. Logging style
7. Event recording
8. Status update pattern
9. Condition helpers
10. Resource creation
11. Error handling and wrapping
12. Constants location
```

---

### Phase 6: Generate Controller Code

Based on OPERATOR_TYPE and extracted requirements, generate the controller.

#### 6.1 For controller-runtime Based Operators

Generate: `<target-path>/<resource>_controller.go`

Key components:

- **RBAC markers** generated dynamically from Phase 3 extraction
- **Reconciler struct** with `client.Client`, `Scheme`, `Recorder`
- **Reconcile method** with actual logic:
  1. Fetch the resource instance
  2. Check for deletion (handle finalizer cleanup)
  3. Add finalizer if needed
  4. Set Progressing condition
  5. Execute main reconciliation logic
  6. Set success conditions and update status
- **reconcile() method** with EP-derived business logic:
  1. Validate spec
  2. Reconcile each dependent resource
  3. Check/update external state (if applicable)
  4. Update observed status
- **Dependent resource reconcilers** for each resource from EP:
  - `reconcile<Resource>()` -- get-or-create with owner references
  - `build<Resource>()` -- construct desired state from spec
  - `<resource>NeedsUpdate()` -- compare existing vs desired
- **reconcileDelete()** -- cleanup handler with finalizer removal
- **setCondition()** -- status condition helper
- **SetupWithManager()** -- watches for primary and owned resources

#### 6.2 For library-go Based Operators

Generate: `pkg/operator/<resource>/<resource>_controller.go`

Key components:

- **Controller struct** with client, kubeClient, operatorClient, eventRecorder
- **New<Resource>Controller()** using `factory.New().WithSync().WithInformers()`
- **sync() method** with klog, informer-based gets, status condition updates
  via `v1helpers.UpdateStatus()`

---

### Phase 7: Register Controller with Manager

#### 7.1 For controller-runtime

Locate `main.go` or `cmd/main.go` and add:

- Import for the controller package
- Controller setup call in `main()` after manager creation

#### 7.2 For library-go

Locate `pkg/operator/starter.go` and add:

- Import for the new controller package
- Controller construction and registration

---

### Phase 8: Generate Feature Gate Check (if applicable)

If the enhancement specifies a FeatureGate, add a check at the start of
Reconcile/Sync that returns early when disabled.

---

### Phase 9: Output Summary

Write `artifacts/operator-feature-dev/impl/implementation-summary.md`:

```text
=== Controller Implementation Summary ===

Input Sources:
  Enhancement PR: <url> (if provided)
  Design Document: <gist-url> (if provided)
Operator Type: <controller-runtime | library-go>

Generated Files:
  - <path/to/controller.go> -- Main controller implementation
  - <path/to/main.go> -- Updated with controller registration

Controller Details:
  Package: <package name>
  API Group: <group.openshift.io>
  API Version: <version>
  Kind: <KindName>

Reconciliation Workflow:
  1. Validate spec
  2. <step from EP>
  ...
  N. Update status

Dependent Resources Managed:
  - <ResourceType>: <name-pattern> -- <purpose>

Status Conditions:
  - Available: Set True when <criteria>
  - Progressing: Set True during reconciliation
  - Degraded: Set True on errors

Events Recorded:
  - Normal/Created, Normal/Updated, Normal/ReconcileComplete
  - Warning/ReconcileFailed

RBAC Permissions Generated:
  - <group>/<resource>: get, list, watch
  - <group>/<resource>/status: get, update, patch
  - <dependent resources>: get, list, watch, create, update, patch, delete
  - core/events: create, patch

Watches Configured:
  - Primary: <Kind>
  - Owned: <dependent resource types>

Cleanup on Deletion:
  - Kubernetes resources: owner references
  - External resources: <if any>

Feature Gate: <FeatureGateName> (if applicable)

Next Steps:
  1. Review the generated controller code
  2. Run 'make generate' to update generated code
  3. Run 'make manifests' to update RBAC/CRD manifests
  4. Run 'make build' to verify compilation
  5. Run 'make test' to run unit tests
  6. Run 'make lint' to check for issues
```

## Critical Failure Conditions

1. **No input provided**: Neither EP URL nor design document URL
2. **Invalid PR URL**: Not a valid `openshift/enhancements` PR
3. **Invalid gist URL**: Not a valid GitHub Gist
4. **Missing tools**: `gh`, `go`, `git`, or `make` not installed
5. **Not authenticated**: `gh` not authenticated
6. **Not an operator repo**: No go.mod or unrecognized operator type
7. **No API types**: Types don't exist (run `/oape.api-generate` first)
8. **Input not accessible**: EP or design document cannot be fetched
9. **No implementation requirements**: Input sources don't describe controller
   behavior
10. **Ambiguous requirements**: Cannot determine reconciliation workflow
11. **Unsupported framework**: Not controller-runtime or library-go

## Behavioral Rules

1. **Never guess**: If input sources are ambiguous, STOP and ask.
2. **Design document precedence**: Design document takes precedence for
   implementation details.
3. **Zero TODOs**: Generate actual implementation, not placeholders.
4. **Convention over proposal**: Apply framework best practices even if input
   sources differ.
5. **Match existing patterns**: Replicate patterns from existing controllers.
6. **Idempotent reconciliation**: Generated Reconcile() must be idempotent.
7. **Minimal changes**: Only generate what the input sources require.
8. **Surgical edits**: Preserve unrelated code when modifying files.
9. **Status-first**: Always use `Status().Update()` for status changes.
10. **Finalizer safety**: Add before external resources, remove after cleanup.
11. **Event recording**: Record events for user-visible state changes.

## Output

- Generated controller code in the operator repository
- Updated manager registration (main.go or starter.go)
- Summary saved to `artifacts/operator-feature-dev/impl/implementation-summary.md`
