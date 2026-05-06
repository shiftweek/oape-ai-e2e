# /oape.api-generate - Generate API type definitions from an Enhancement Proposal

## Purpose

Read an OpenShift Enhancement Proposal PR and/or a design document, extract the
required API changes, and generate compliant Go type definitions in the correct
paths of the current operator repository. Refreshes API conventions from
authoritative sources on every run.

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

# Extract --design-doc argument if present
if echo "$ARGS" | grep -q '\-\-design-doc'; then
  DESIGN_DOC_URL=$(echo "$ARGS" | sed -n 's/.*--design-doc[[:space:]]\+\([^[:space:]]\+\).*/\1/p')
  ENHANCEMENT_PR=$(echo "$ARGS" | sed 's/--design-doc[[:space:]]\+[^[:space:]]\+//' | xargs)
else
  ENHANCEMENT_PR="$ARGS"
fi

if [ -z "$ENHANCEMENT_PR" ] && [ -z "$DESIGN_DOC_URL" ]; then
  echo "PRECHECK FAILED: No input provided."
  echo "Usage: /oape.api-generate <EP_URL> [--design-doc <GIST_URL>]"
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

if [ -n "$MISSING_TOOLS" ]; then
  echo "PRECHECK FAILED: Missing required tools:$MISSING_TOOLS"
  exit 1
fi

if ! gh auth status &> /dev/null 2>&1; then
  echo "PRECHECK FAILED: GitHub CLI is not authenticated."
  echo "Run 'gh auth login' to authenticate."
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

if grep -q "github.com/openshift/api" "$REPO_ROOT/go.mod"; then
  echo "Confirmed: Repository depends on github.com/openshift/api"
elif echo "$GO_MODULE" | grep -q "github.com/openshift/api"; then
  echo "Confirmed: This IS the openshift/api repository."
else
  echo "PRECHECK FAILED: Not an OpenShift operator repository."
  echo "go.mod does not reference github.com/openshift/api."
  exit 1
fi
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

#### Precheck 6 -- Verify Clean Working Tree (Warning)

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

### Phase 1: Refresh Knowledge -- Fetch Latest API Conventions

Fetch and read BOTH documents in full BEFORE generating any code. Never rely on
cached knowledge.

1. **OpenShift API Conventions**: `https://raw.githubusercontent.com/openshift/enhancements/master/dev-guide/api-conventions.md`
2. **Kubernetes API Conventions**: `https://raw.githubusercontent.com/kubernetes/community/master/contributors/devel/sig-architecture/api-conventions.md`

```thinking
Read both fetched convention documents in full. Extract every rule that applies
to API type generation: field markers, naming, documentation, validation,
pointers, unions, enums, TechPreview gating, etc. The fetched documents are the
single source of truth. If conventions have been updated since this command was
written, the freshly fetched versions take precedence.
```

### Phase 2: Fetch and Analyze Input Sources

#### 2.1 Fetch Enhancement Proposal (if provided)

```bash
if [ -n "$ENHANCEMENT_PR_NUMBER" ]; then
  gh pr view "$ENHANCEMENT_PR_NUMBER" --repo openshift/enhancements --json files --jq '.files[].path'
fi
```

Fetch full content of each proposal file using the PR ref:

```bash
gh api "repos/openshift/enhancements/contents/<path>?ref=refs/pull/$ENHANCEMENT_PR_NUMBER/head" --jq '.content' | base64 -d
```

Fallbacks if above fails:

```bash
# Fallback 1: Raw content
curl -sL "https://raw.githubusercontent.com/openshift/enhancements/refs/pull/$ENHANCEMENT_PR_NUMBER/head/<path>"

# Fallback 2: PR diff
gh pr diff "$ENHANCEMENT_PR_NUMBER" --repo openshift/enhancements
```

#### 2.2 Fetch Design Document (if provided)

```bash
if [ -n "$GIST_ID" ]; then
  gh api "gists/$GIST_ID" --jq '.files | to_entries[] | "=== FILE: \(.key) ===\n\(.value.content)\n"'
fi
```

#### 2.3 Analyze and Merge Requirements

```thinking
Extract from the combined sources:
  a. Which operator/component is being modified
  b. API group and version
  c. Whether this is NEW or modifications to EXISTING types
  d. Configuration API vs Workload API
  e. Fields being added or modified
  f. Validation requirements (enums, patterns, min/max, cross-field)
  g. TechPreview gating
  h. Discriminated unions
  i. Defaulting behavior
  j. Immutability requirements
  k. Status fields and conditions
  l. FeatureGate name

Design document takes precedence over EP for implementation details.
If conflicts are ambiguous, ask the user.
```

### Phase 3: Identify Target API Paths

Detect the repository layout pattern:

#### Known Layout Patterns

**Pattern 1 -- openshift/api repository:**

```text
<group>/<version>/types_<resource>.go
<group>/<version>/doc.go
<group>/<version>/register.go
<group>/<version>/tests/<crd-name>/*.testsuite.yaml
features/features.go
```

**Pattern 2 -- Operator repo with group subdirectory:**

```text
api/<group>/<version>/<resource>_types.go
api/<group>/<version>/groupversion_info.go
```

**Pattern 3 -- Operator repo with flat version directory:**

```text
api/<version>/<resource>_types.go
api/<version>/groupversion_info.go
```

#### Detect the Pattern

```bash
# Find type definition files
find "$REPO_ROOT" -type f \( -name 'types*.go' -o -name '*_types.go' \) \
  -not -path '*/vendor/*' -not -path '*/_output/*' -not -path '*/zz_generated*' | head -40

# Find registration files
find "$REPO_ROOT" -type f \( -name 'doc.go' -o -name 'register.go' -o -name 'groupversion_info.go' \) \
  -not -path '*/vendor/*' | head -40

# Find CRD manifests
find "$REPO_ROOT" -type f -name '*.crd.yaml' -not -path '*/vendor/*' | head -20

# Find test suites
find "$REPO_ROOT" -type f -name '*.testsuite.yaml' -not -path '*/vendor/*' | head -20

# Find feature gate definitions
find "$REPO_ROOT" -type f -name 'features.go' -not -path '*/vendor/*' | head -10
```

### Phase 4: Read Existing API Types for Context

Read existing types in the target package to match style exactly:

```thinking
Read existing types file(s) to:
1. Match coding style exactly
2. Understand existing struct hierarchy
3. Know where to insert new fields or types
4. Identify existing fields that need modification
5. Identify existing imports to reuse
6. See how feature gates are applied
7. Understand existing validation patterns
```

### Phase 5: Generate or Modify API Type Definitions

Generate or modify Go type definitions based on the input sources. This may
include new types, new fields, modifications to existing fields, enum types,
discriminated unions, or type registration.

For every marker, tag, or convention applied: derive it from the fetched
convention documents (Phase 1) or existing code (Phase 4). Conventions take
precedence when both differ.

Determine whether this is a **Configuration API** or **Workload API** -- the
conventions define different rules for each.

After generating, review every changed line against conventions. If any
violation has a convention-compliant alternative, apply it and note the
deviation in the summary.

### Phase 6: Add FeatureGate Registration (if applicable)

If the repository contains a `features.go` file, read it and add a new
FeatureGate following the existing pattern.

If no `features.go` exists and the enhancement requires a FeatureGate, note
this in the summary and advise where to register it.

### Phase 7: Output Summary

Write `artifacts/operator-feature-dev/api/generation-summary.md`:

```text
=== API Generation Summary ===

Input Sources:
  Enhancement PR: <url> (if provided)
  Design Document: <gist-url> (if provided)

Generated/Modified Files:
  - <path/to/types_resource.go> -- <description>
  - <path/to/features/features.go> -- <FeatureGate added> (if applicable)

API Group: <group.openshift.io>
API Version: <version>
Kind: <KindName>
Resource: <resourcename>
Scope: <Cluster|Namespaced>
FeatureGate: <FeatureGateName>

New Types Added:
  - <TypeName> -- <description>

New Fields Added:
  - <ParentType>.<fieldName> (<type>) -- <description>

Modified Fields/Types:
  - <ParentType>.<fieldName> -- <what changed and why>

Validation Rules:
  - <field>: <rule description>

Source Conflicts Resolved: (if both EP and design doc provided)
  - <field>: Used design doc specification (<reason>)

Next Steps:
  1. Review the generated code
  2. Run 'make update' to regenerate CRDs and deep copy functions
  3. Run 'make verify' to validate generated code
  4. Run 'make lint' to check for kube-api-linter issues
  5. If FeatureGate was added, verify it appears in the feature gate list
```

## Critical Failure Conditions

1. **No input provided**: Neither EP URL nor design document URL
2. **Invalid PR URL**: Not a valid `openshift/enhancements` PR
3. **Invalid gist URL**: Not a valid GitHub Gist
4. **Missing tools**: `gh`, `go`, or `git` not installed or `gh` unauthenticated
5. **Not an operator repo**: Not a Git repository with Go module referencing
   `openshift/api`
6. **Input not accessible**: EP or design document cannot be fetched
7. **No API changes found**: Input sources don't describe API changes
8. **Ambiguous API target**: Cannot determine target API group, version, or kind

## Behavioral Rules

1. **Never guess**: If input sources are ambiguous about API details, STOP and
   ask the user.
2. **Design document precedence**: Design document takes precedence for
   implementation details.
3. **Convention over proposal**: If input sources suggest an API design that
   violates conventions (e.g., using a Boolean), generate the
   convention-compliant alternative and document the deviation.
4. **TechPreview when specified**: If input sources indicate TechPreview gating,
   generate the appropriate FeatureGate markers.
5. **Idempotent**: Running multiple times with the same inputs should produce
   the same result.
6. **Minimal changes**: Only generate what the input sources specify.
7. **Surgical edits**: When modifying existing files, preserve all unrelated
   code, comments, and formatting.

## Output

- Generated/modified Go type files in the operator repository
- Summary saved to `artifacts/operator-feature-dev/api/generation-summary.md`
