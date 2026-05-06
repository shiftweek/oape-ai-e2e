# /oape.init - Clone and validate an operator repository

## Purpose

Clone an OpenShift operator Git repository, checkout the specified base branch,
and validate it is a Go-based operator with a recognized framework. This is the
first step in the operator feature development workflow.

## Arguments

- `$ARGUMENTS`: `<repo-url> <base-branch>`

## Process

### Phase 0: Prechecks

All prechecks must pass before proceeding. If ANY fails, STOP immediately.

#### Precheck 1 -- Validate Arguments

Both a git URL and a base branch MUST be provided.

```bash
GIT_URL=$(echo "$ARGUMENTS" | awk '{print $1}')
BASE_BRANCH=$(echo "$ARGUMENTS" | awk '{print $2}')

if [ -z "$GIT_URL" ] || [ -z "$BASE_BRANCH" ]; then
  echo "PRECHECK FAILED: Both a git URL and a base branch are required."
  echo "Usage: /oape.init <repo-url> <base-branch>"
  echo ""
  echo "Example:"
  echo "  /oape.init https://github.com/openshift/cert-manager-operator main"
  exit 1
fi

echo "Git URL: $GIT_URL"
echo "Base branch: $BASE_BRANCH"
```

#### Precheck 2 -- Verify Required Tools

```bash
MISSING_TOOLS=""

if ! command -v git &> /dev/null; then
  MISSING_TOOLS="$MISSING_TOOLS git"
fi

if [ -n "$MISSING_TOOLS" ]; then
  echo "PRECHECK FAILED: Missing required tools:$MISSING_TOOLS"
  exit 1
fi

echo "Required tools are available."
```

**If ALL prechecks passed, proceed to Phase 1.**

---

### Phase 1: Derive Clone Directory

```bash
CLONE_DIR=$(basename "$GIT_URL" .git)
CLONE_URL="$GIT_URL"

echo "Clone directory: $CLONE_DIR"
echo "Clone URL: $CLONE_URL"
```

---

### Phase 2: Clone Repository

Clone using `git clone --filter=blob:none`. Handle the case where the target
directory already exists.

```bash
if [ -d "$CLONE_DIR" ]; then
  echo "Directory '$CLONE_DIR' already exists."

  EXISTING_REMOTE=$(git -C "$CLONE_DIR" remote get-url origin 2>/dev/null || true)

  if [ -n "$EXISTING_REMOTE" ]; then
    # Normalize URLs for comparison
    NORM_EXISTING=$(echo "$EXISTING_REMOTE" | sed 's/\.git$//' | sed 's:/$::')
    NORM_CLONE=$(echo "$CLONE_URL" | sed 's/\.git$//' | sed 's:/$::')

    if [ "$NORM_EXISTING" = "$NORM_CLONE" ]; then
      echo "Existing directory is already a clone of the same repository."
      echo "Using existing directory as-is."
    else
      echo "FAILED: Directory '$CLONE_DIR' exists but points to a different remote."
      echo "  Expected: $CLONE_URL"
      echo "  Found:    $EXISTING_REMOTE"
      echo ""
      echo "Options:"
      echo "  1. Remove the directory manually: rm -rf $CLONE_DIR"
      echo "  2. Use a different working directory"
      exit 1
    fi
  else
    echo "FAILED: Directory '$CLONE_DIR' exists but is not a git repository."
    echo ""
    echo "Options:"
    echo "  1. Remove the directory manually: rm -rf $CLONE_DIR"
    echo "  2. Use a different working directory"
    exit 1
  fi
else
  echo "Cloning $CLONE_URL into $CLONE_DIR..."
  git clone --filter=blob:none "$CLONE_URL"

  if [ $? -ne 0 ]; then
    echo "FAILED: git clone failed."
    echo "Check your network connection and repository access."
    exit 1
  fi

  echo "Clone complete."
fi
```

---

### Phase 3: Checkout Base Branch and Verify

Change into the cloned directory, checkout the base branch, and verify it is a
valid Go-based operator.

```bash
cd "$CLONE_DIR" || { echo "FAILED: Cannot change to directory $CLONE_DIR"; exit 1; }

git checkout "$BASE_BRANCH" || { echo "FAILED: Cannot checkout branch '$BASE_BRANCH'"; exit 1; }
echo "Checked out branch: $BASE_BRANCH"

# Verify Go module
if [ -f "go.mod" ]; then
  GO_MODULE=$(head -1 go.mod | awk '{print $2}')
  echo "Go module: $GO_MODULE"
else
  echo "WARNING: No go.mod found. This may not be a Go-based operator repository."
  GO_MODULE="(not detected)"
fi

# Detect operator framework
FRAMEWORK="unknown"
if [ -f "go.mod" ]; then
  if grep -q "sigs.k8s.io/controller-runtime" go.mod 2>/dev/null; then
    FRAMEWORK="controller-runtime"
  elif grep -q "github.com/openshift/library-go" go.mod 2>/dev/null; then
    FRAMEWORK="library-go"
  fi
fi

echo "Framework: $FRAMEWORK"
echo "Current directory: $(pwd)"
```

---

### Phase 4: Output Summary

Write `artifacts/operator-feature-dev/init-summary.md`:

```text
=== Repository Init Summary ===

Repository:  <clone-dir>
Clone URL:   <clone-url>
Base Branch: <base-branch>
Local Path:  <absolute-path-to-cloned-dir>
Go Module:   <module-name>
Framework:   <controller-runtime | library-go | unknown>
```

## Critical Failure Conditions

1. **Missing arguments**: Git URL or base branch not provided
2. **Missing tools**: `git` not installed
3. **Clone failed**: Network, permissions, or invalid URL
4. **Branch checkout failed**: Base branch does not exist
5. **Directory conflict**: Target directory exists but is not a clone of the
   expected repository

## Behavioral Rules

1. **Efficient cloning**: Always use `git clone --filter=blob:none`.
2. **Non-destructive**: Never delete an existing directory automatically.
3. **Idempotent**: If the directory already exists and is a clone of the correct
   repository, use it as-is.

## Output

- Init summary printed to user
- Summary saved to `artifacts/operator-feature-dev/init-summary.md`
