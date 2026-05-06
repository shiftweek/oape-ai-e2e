---
name: effective-go
description: Ensures all generated Go code follows best practices from the official Effective Go documentation and Go community standards.
---

# Effective Go

Ensures all generated Go code follows best practices from the official Effective
Go documentation and Go community standards.

## When This Skill Applies

- Generating API type definitions (`/oape.api-generate`)
- Generating controller/reconciler code (`/oape.api-implement`)
- Generating tests (`/oape.api-generate-tests`, `/oape.e2e-generate`)
- Any Go code generation or modification

## Guidelines

### 1. Formatting

Always format code with `gofmt` standards. Consistent indentation, spacing
around operators, and brace placement.

### 2. Naming Conventions

- Use `MixedCaps` for exported identifiers, `mixedCaps` for unexported
- Never use underscores in Go names
- Acronyms should be consistent case: `HTTP`, `URL`, `ID` (not `Http`, `Url`, `Id`)
- Package names: short, lowercase, single-word (no `util`, `common`, `misc`)

### 3. Error Handling

- Always check errors explicitly — never ignore with `_`
- Return errors, don't panic (except truly unrecoverable situations)
- Wrap errors with context: `fmt.Errorf("context: %w", err)`
- Error messages: lowercase, no punctuation, specific about what failed

### 4. Documentation

- Document all exported functions, types, and constants
- Start comments with the name of the thing being documented
- Use complete sentences

### 5. Interfaces

- Keep interfaces small (1-3 methods)
- Accept interfaces, return concrete types
- Define interfaces where they're used, not where they're implemented
- Name single-method interfaces with `-er` suffix

### 6. Concurrency

- Share memory by communicating (use channels)
- Use `sync.Mutex` only when channels are impractical
- Always handle context cancellation
- Track goroutines with WaitGroup/ErrGroup

### 7. Imports

- Group imports: standard library, external, internal
- Use blank lines to separate groups
- Use aliases only when necessary (conflicts, clarity)

```go
import (
    "context"
    "fmt"

    corev1 "k8s.io/api/core/v1"
    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
    ctrl "sigs.k8s.io/controller-runtime"
    "sigs.k8s.io/controller-runtime/pkg/client"

    configv1 "github.com/openshift/api/config/v1"
    "github.com/myorg/myoperator/internal/controller"
)
```

### 8. Variable Declarations

- Use short declarations (`:=`) inside functions
- Use `var` for package-level variables or zero values
- Group related declarations with `const()` and `var()` blocks

### 9. Receiver Names

- Use short, consistent receiver names (1-2 letters)
- Use the same receiver name throughout the type's methods
- Never use `this` or `self`

### 10. Zero Values

- Leverage zero values for initialization
- Design types so zero value is useful
- Check for zero value before applying defaults

### 11. Slices and Maps

- Pre-allocate slices with `make` when length is known
- Avoid nil slice vs empty slice confusion
- Use `maps.Clone` and `slices.Clone` for copies

### 12. Receiver Types

- Use pointer receivers for methods that modify state
- Use value receivers for methods that don't modify state
- Be consistent within a type — don't mix unless there's a clear reason

## References

- [Effective Go](https://go.dev/doc/effective_go)
- [Go Code Review Comments](https://github.com/golang/go/wiki/CodeReviewComments)
- [Go Proverbs](https://go-proverbs.github.io/)

## Usage by Other Commands

This skill is referenced by:

- `/oape.api-generate` — when generating API type definitions
- `/oape.api-implement` — when generating controller code
- `/oape.api-generate-tests` — when generating test code
- `/oape.e2e-generate` — when generating E2E test code

All Go code generation MUST follow these guidelines.
