# /oape.api-generate-tests - Generate integration tests for API types

## Purpose

Generate `.testsuite.yaml` integration test files for OpenShift API type
definitions. Reads Go type definitions, CRD manifests, and validation markers
to produce comprehensive test suites covering create, update, validation, and
error scenarios.

This command should be run AFTER API types and CRD manifests have been generated.

## Arguments

- `$ARGUMENTS`: `<path-to-types-file-or-api-directory>`

## Process

### Phase 0: Prechecks

All prechecks must pass before proceeding. If ANY fails, STOP immediately.

#### Precheck 1 -- Verify Repository and Tools

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
echo "Repository root: $REPO_ROOT"
echo "Go module: $GO_MODULE"
```

#### Precheck 2 -- Identify Target API Types

```bash
TARGET_PATH="$ARGUMENTS"

if [ -z "$TARGET_PATH" ]; then
  echo "PRECHECK FAILED: No target path provided."
  echo "Usage: /oape.api-generate-tests <path-to-types-file-or-api-directory>"
  exit 1
fi
```

```thinking
Determine which API types to generate tests for:
1. User provided a specific types file path -> use it directly
2. User provided an API directory -> find all types files in it

Extract: API group, version, kind, resource plural, all fields with types,
validation markers, and godoc.
```

#### Precheck 3 -- Verify CRD Manifests Exist

```bash
# For openshift/api repos
find "$REPO_ROOT" -type d -name 'zz_generated.crd-manifests' -not -path '*/vendor/*' | head -5

# For operator repos
find "$REPO_ROOT" -type d -name 'bases' -path '*/crd/*' -not -path '*/vendor/*' | head -5
```

If no CRD manifests found:

```text
WARNING: No CRD manifests found. Run 'make update' or 'make manifests' first.
Test suites reference CRD manifests -- tests will fail without them.
```

---

### Phase 1: Read API Types and CRD Manifests

Read the target Go types file(s) and extract all information needed for test
generation:

```thinking
From the Go types, extract every field, type, marker, and validation rule:
1. Top-level CRD types (structs with +kubebuilder:object:root=true or +genclient)
2. For each CRD type: kind, API group, version, resource plural, scope, singleton
3. Every spec and status field: name, type, optional/required, pointer semantics
4. All validation markers: enums, min/max, minLength/maxLength, minItems/maxItems,
   pattern, format, XValidation CEL rules
5. Enum types and allowed values
6. Discriminated unions: discriminator field, member types
7. Immutable fields (XValidation rules referencing oldSelf)
8. Default values
9. Feature gate annotations (+openshift:enable:FeatureGate)
10. Nested object validation
11. Map key/value constraints
12. Any other kubebuilder or OpenShift marker

The list above is guidance, not exhaustive. Extract ALL markers found.
```

Also read CRD manifest(s) to get: full CRD name, OpenAPI v3 schema, feature
set annotations.

### Phase 2: Identify Test Directory and Existing Tests

Determine where test files should be placed:

**openshift/api:**

```text
<group>/<version>/tests/<plural>.<group>/
```

**Operator repos:**

```text
api/<version>/tests/<plural>.<group>/
```

or

```text
api/<group>/<version>/tests/<plural>.<group>/
```

Check for existing test files to avoid duplicating tests.

### Phase 3: Generate Test Suites

Generate `.testsuite.yaml` files covering these categories. Derive specific test
cases from the types and validation rules read in Phase 1.

#### Category 1 -- Minimal Valid Create

Every test suite MUST include at least one test that creates a minimal valid
instance with only required fields populated.

#### Category 2 -- Valid Field Values

For each field in the spec:

- Test that valid values are accepted and persisted correctly
- For enum fields: test each allowed enum value
- For optional fields: test with and without the field
- For fields with defaults: verify the default is applied

#### Category 3 -- Invalid Field Values (Validation Failures)

For each field with validation rules:

- Enum fields: test a value not in the allowed set -> `expectedError`
- Pattern fields: test a value that doesn't match -> `expectedError`
- Min/max constraints: test values at and beyond boundaries -> `expectedError`
- Required fields: test omission -> `expectedError`
- CEL validation rules: test inputs that violate each rule -> `expectedError`

#### Category 4 -- Update Scenarios

For fields that can be updated:

- Test valid updates (change field value) -> `expected`
- For immutable fields: test that updates are rejected -> `expectedError`
- For fields with update-specific validation: test boundary cases

#### Category 5 -- Singleton Name Validation

If the CRD is a cluster-scoped singleton (name must be "cluster"):

- Test creation with `resourceName: cluster` -> success
- Test creation with `resourceName: not-cluster` -> `expectedError`

#### Category 6 -- Discriminated Unions

If the type uses discriminated unions:

- Test each valid discriminator + member combination -> `expected`
- Test mismatched discriminator + member -> `expectedError`
- Test missing required member -> `expectedError`

#### Category 7 -- Feature-Gated Fields

If fields are gated behind a FeatureGate:

- Stable/default test suite: setting gated field is rejected -> `expectedError`
- TechPreview test suite: gated field is accepted -> `expected`

#### Category 8 -- Status Subresource

If the type has a status subresource:

- Test valid status updates
- Test invalid status updates -> `expectedStatusError`

#### Category 9 -- Additional Coverage

```thinking
Re-examine every marker, annotation, CEL rule, godoc comment, and structural
detail. Ask: is there any validation behavior or edge case NOT already covered?

Examples: cross-field dependencies, mutually exclusive fields, nested object
validation, list item uniqueness, map key/value constraints, string format
validations, complex CEL rules, defaulting interactions, zero values vs nil.
```

### Phase 4: Write Test Suite Files

Write `.testsuite.yaml` file(s) following this format:

```yaml
apiVersion: apiextensions.k8s.io/v1
name: "<DisplayName>"
crdName: <plural>.<group>
tests:
  onCreate:
    - name: Should be able to create a minimal <Kind>
      initial: |
        apiVersion: <group>/<version>
        kind: <Kind>
        spec: {}
      expected: |
        apiVersion: <group>/<version>
        kind: <Kind>
        spec: {}
    - name: Should reject <Kind> with invalid <fieldName>
      initial: |
        apiVersion: <group>/<version>
        kind: <Kind>
        spec:
          <fieldName>: <invalidValue>
      expectedError: "<expected error substring>"
  onUpdate:
    - name: Should not allow changing immutable field <fieldName>
      initial: |
        apiVersion: <group>/<version>
        kind: <Kind>
        spec:
          <fieldName>: <value1>
      updated: |
        apiVersion: <group>/<version>
        kind: <Kind>
        spec:
          <fieldName>: <value2>
      expectedError: "<expected error substring>"
```

#### File Naming Conventions

Derive from existing patterns:

**openshift/api repos:**

- `stable.<kind>.testsuite.yaml`
- `techpreview.<kind>.testsuite.yaml`
- `stable.<kind>.<context>.testsuite.yaml`

**Operator repos:**

- `<kind>.testsuite.yaml`

### Phase 5: Output Summary

Write `artifacts/operator-feature-dev/api/test-generation-summary.md`:

```text
=== API Test Generation Summary ===

Target API: <group>/<version> <Kind>
CRD Name: <plural>.<group>

Generated Test Files:
  - <path/to/testsuite.yaml> -- <N> onCreate tests, <N> onUpdate tests

Test Coverage:
  onCreate:
    - Minimal valid create
    - <field>: valid values (<count> tests)
    - <field>: invalid values (<count> tests)
    - Singleton name validation
  onUpdate:
    - Immutable field <field>: rejected
    - Valid update for <field>

Next Steps:
  1. Review the generated test suites
  2. Run the integration tests
  3. Verify coverage: make verify
  4. Add additional edge-case tests as needed
```

## Behavioral Rules

1. **Derive from source**: All test values and expectations MUST come from
   actual Go types, validation markers, and CRD manifests.
2. **Match existing style**: If the repo has test suites, match their naming,
   formatting, and detail level exactly.
3. **Comprehensive but focused**: Test every field and validation rule found,
   but don't invent scenarios not supported by the schema.
4. **Error messages**: For `expectedError` fields, use substrings from the
   actual CRD validation rules.
5. **Minimal YAML**: Include only fields relevant to each specific test case.
6. **Surgical additions**: When adding to an existing suite, preserve all
   existing tests and append new ones.

## Output

- Generated `.testsuite.yaml` files in the appropriate test directory
- Summary saved to `artifacts/operator-feature-dev/api/test-generation-summary.md`
