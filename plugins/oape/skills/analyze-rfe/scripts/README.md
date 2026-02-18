# Component Context Analysis Scripts

Automated scripts for gathering comprehensive component context using GitHub CLI.

## Overview

These scripts implement the comprehensive component context gathering described in `SKILL.md` Step 2.7. They analyze OpenShift component repositories remotely (without cloning) to extract:

- Repository structure and architecture
- Implementation patterns
- Historical design decisions from PRs
- Lessons learned from issues
- Risk factors and recommendations

## Scripts

### 1. `gather_component_context.py` (Main Orchestrator)

**Purpose**: Main entry point that coordinates all analysis steps.

**Usage**:
```bash
# Analyze single component
./gather_component_context.py cert-manager

# Analyze with RFE keywords for relevant PR search
./gather_component_context.py cert-manager --keywords "certificate rotation" "ACME"

# Analyze multiple components
./gather_component_context.py hypershift cert-manager --keywords "certificate" -v

# Output to file
./gather_component_context.py cert-manager -o output.md

# Get JSON output for programmatic use
./gather_component_context.py cert-manager --json -o output.json
```

**Options**:
- `--keywords`: Keywords from RFE for PR search
- `--max-prs N`: Maximum PRs to search (default: 10)
- `--deep-dive N`: PRs to analyze in detail (default: 3)
- `--analyze-upstream`: Always analyze upstream repositories (skip prompt)
- `--skip-upstream`: Never analyze upstream repositories (skip prompt)
- `--analyze-operands`: Always analyze operand repositories (skip prompt)
- `--skip-operands`: Never analyze operand repositories (skip prompt)
- `--no-interactive`: Non-interactive mode (don't prompt, default: skip upstream & operands)
- `--cache-dir PATH`: Cache directory for GitHub API results
- `-o FILE`: Output file
- `--json`: Output JSON instead of markdown
- `-v, --verbose`: Enable verbose output

### 2. `github_repo_analyzer.py`

**Purpose**: Discovers and analyzes repository structure.

**Features**:
- Discovers downstream/upstream/related repositories
- Detects architecture pattern (Operator, CLI, Library, Service)
- Extracts CRDs, controllers, and key packages
- All via GitHub API (no cloning)

**Standalone Usage**:
```bash
./github_repo_analyzer.py cert-manager
```

### 3. `github_pr_analyzer.py`

**Purpose**: Analyzes PR history for design insights.

**Features**:
- Searches PRs by keywords with relevance ranking
- Extracts design sections, rationale, trade-offs
- Identifies lessons learned
- Finds Architecture Decision Records (ADRs)
- Estimates effort from PR metrics

**Standalone Usage**:
```bash
./github_pr_analyzer.py openshift/cert-manager-operator certificate rotation
```

### 4. `context_synthesizer.py`

**Purpose**: Synthesizes all data into markdown format.

**Features**:
- Combines repository, structure, and PR data
- Generates comprehensive component context
- Formats as markdown per SKILL.md spec
- Extracts patterns, risks, and recommendations

**Standalone Usage**:
```bash
./context_synthesizer.py cert-manager
```

### 5. `operand_discovery.py`

**Purpose**: Discovers operand repositories managed by operators.

**Features**:
- Detects if a repository is an operator
- Discovers operands from README, manifests, and OLM metadata
- Enriches operands with repository information
- Supports OpenShift's operator-operand pattern

**Standalone Usage**:
```bash
./operand_discovery.py openshift/cluster-monitoring-operator
```

**Why needed**: In OpenShift, operators manage operands (workloads). An RFE may require changes in the operator (lifecycle/configuration) or operands (core functionality). Analyzing both provides complete context.

## Operator-Operand Analysis

See [OPERATOR_OPERAND_ANALYSIS.md](../OPERATOR_OPERAND_ANALYSIS.md) for comprehensive guide on operator-operand analysis.

**Summary**: When a component is an operator managing operands (e.g., `cluster-monitoring-operator` manages `prometheus`, `alertmanager`), the script can optionally analyze all operand repositories to provide holistic understanding of where to implement RFEs.

## Prerequisites

### Required Tools

1. **GitHub CLI (`gh`)**:
   ```bash
   # Install
   # macOS
   brew install gh

   # Linux
   sudo dnf install gh  # Fedora/RHEL
   sudo apt install gh  # Ubuntu/Debian

   # Authenticate
   gh auth login
   ```

2. **Python 3.7+** with no external dependencies (uses stdlib only)

### Verify Setup

```bash
# Check gh CLI is authenticated
gh auth status

# Should show:
# ✓ Logged in to github.com as <your-username>
```

## How It Works

## Upstream Repository Analysis

### When Upstream Analysis is Useful

When a component has an upstream repository (e.g., `cert-manager/cert-manager` for OpenShift's `cert-manager-operator`), you can optionally analyze it to gain additional insights:

**Use cases for upstream analysis**:
- **Upstream adoption RFEs**: Understanding features being adopted from upstream
- **Feature parity analysis**: Identifying upstream capabilities not in OpenShift
- **Cross-project alignment**: Comparing architectural approaches
- **Design validation**: Reviewing original design decisions
- **Contribution planning**: Finding opportunities to contribute back to upstream

**When to skip upstream analysis**:
- **OpenShift-only features**: No upstream equivalent exists
- **Time-constrained**: Quick analysis needed
- **Known divergence**: Component intentionally differs from upstream

### How It Works

When an upstream repository is discovered, the script will prompt:

```
======================================================================
Upstream Repository Found for cert-manager
======================================================================
Upstream: cert-manager/cert-manager

Upstream analysis includes:
  - Codebase structure and architecture
  - Historical PR analysis and design decisions
  - Architecture Decision Records (ADRs)

This is useful for:
  - Understanding original design intent
  - Finding upstream features to adopt
  - Identifying differences between upstream/downstream

Note: This will add ~15-30 seconds to analysis time
======================================================================

Analyze upstream repository 'cert-manager/cert-manager'? [y/N]:
```

### Controlling Upstream Analysis

**Interactive mode** (default):
```bash
# Will prompt for each component with upstream
./gather_component_context.py cert-manager --keywords "certificate"
```

**Always analyze upstream**:
```bash
./gather_component_context.py cert-manager --keywords "certificate" --analyze-upstream
```

**Never analyze upstream**:
```bash
./gather_component_context.py cert-manager --keywords "certificate" --skip-upstream
```

**Non-interactive mode** (skips upstream by default):
```bash
./gather_component_context.py cert-manager --keywords "certificate" --no-interactive
```

### Upstream Analysis Output

When upstream is analyzed, additional sections are added:

```markdown
**Upstream Analysis**:
*Analysis of upstream repository: cert-manager/cert-manager*

**Architecture Comparison**:
- Downstream: Kubernetes Operator
- Upstream: Kubernetes Operator
- API alignment: High

**Upstream Implementation Patterns**:
- Upstream PR #1234: ACME DNS-01 challenge implementation
  - Pattern: Provider interface with pluggable backends

**Upstream Architecture Decisions**:
- ADR-003-certificate-storage: Use Kubernetes secrets for certificate storage

**Upstream Adoption Considerations**:
- Upstream has 7 CRDs vs downstream 5 - consider adopting ClusterIssuer, Challenge
- Review upstream PRs for proven ACME implementation patterns
- Consider contributing OpenShift-specific enhancements back to upstream
```

### Remote Analysis Approach

All scripts use **GitHub CLI** for remote access:

```bash
# Repository discovery
gh repo view openshift/cert-manager-operator

# Browse structure
gh api repos/openshift/cert-manager-operator/contents/pkg

# Search PRs
gh search prs --repo openshift/cert-manager-operator "certificate"

# Get PR details
gh pr view 123 --repo openshift/cert-manager-operator
```

**No cloning required** ✓

### Caching Strategy

Results are cached in `.work/jira/analyze-rfe/cache/` to:
- Respect GitHub API rate limits (5000 req/hour)
- Speed up repeated analysis
- Enable offline inspection

Cache files: `{operation}_{repo}_{query}.json`

## Output Format

### Markdown Output

```markdown
### Component: cert-manager

**Repositories**:
- Downstream: openshift/cert-manager-operator
- Upstream: cert-manager/cert-manager
- Related: ...

**What it does**: ...
**Why it exists**: ...
**How it works**:
- Architecture: Kubernetes Operator
- Key Packages: controllers, api
- API Types (CRDs): Certificate, CertificateRequest

**Key Implementation Patterns**:
1. **Controller Reconciliation**: ...
2. **Certificate Rotation**: ...

**Historical Context**:
**Relevant PRs**:
- PR #456 (2024-06): Add ACME support
  - **Design**: ...
  - **Why**: ...
  - **Scope**: M (15 files changed)

**Risk Factors**:
- **Complexity**: Multiple CRDs increase integration complexity
  - **Mitigation**: ...

**Recommended Approach for RFE Implementation**:
- Follow Kubernetes Operator pattern
- Review PR #456 for similar patterns
- ...
```

### JSON Output

Use `--json` flag for programmatic access:

```json
{
  "component": "cert-manager",
  "repositories": { ... },
  "structure": { ... },
  "pr_insights": [ ... ],
  "adrs": [ ... ],
  "lessons": [ ... ],
  "markdown": "..."
}
```

## Integration with analyze-rfe

The `gather_component_context.py` script is invoked by the `/oape:analyze-rfe` command during **Step 2.7** (Comprehensive Component Context).

**Flow**:
1. RFE fetched and parsed (Step 1-2)
2. Affected components identified (Step 2)
3. **For each component**:
   ```python
   # Extract keywords from RFE
   keywords = extract_rfe_keywords(rfe_data)

   # Run component context gatherer
   context = gather_component_context(
       component_name,
       keywords=keywords,
       max_prs=50,
       deep_dive=3
   )

   # Add to RFE analysis output
   rfe_analysis["comprehensive_context"][component] = context["markdown"]
   ```

## Performance

**Typical Analysis Times**:
- Single component (no PR search): ~5-10 seconds
- Single component (with PR search): ~15-30 seconds
- 3 components with PR search: ~45-90 seconds

**Optimization**:
- Caching reduces subsequent runs to <5 seconds
- GitHub API rate limit: 5000 req/hour (rarely hit)
- Network-dependent (no offline mode without cache)

## Error Handling

### Repository Not Found
```
Warning: No downstream repository found for {component}
```
→ Script continues, outputs "No public repository found for analysis"

### GitHub CLI Not Authenticated
```
Error: GitHub CLI (gh) not found
Install from: https://cli.github.com/
```
→ Script exits, user must install/authenticate `gh`

### API Rate Limit Hit
```
Warning: Command timed out: gh search prs ...
```
→ Script caches what it gathered, notes "analysis incomplete"

## Troubleshooting

### "gh: command not found"
Install GitHub CLI: https://cli.github.com/

### "gh auth status" fails
Authenticate: `gh auth login`

### Cache growing too large
Clear cache: `rm -rf .work/jira/analyze-rfe/cache/`

### PRs not relevant
Refine keywords: Use specific terms from RFE (e.g., "certificate rotation" not just "certificate")

## Configuration

Environment variables (optional):

```bash
# Maximum PRs to search
export ANALYZE_RFE_MAX_PRS=20

# PRs to analyze in detail
export ANALYZE_RFE_DEEP_DIVE_PRS=5

# Cache directory
export ANALYZE_RFE_CACHE_DIR=.work/cache
```

## Examples

### Example 1: Analyze HyperShift for RFE about custom certificates

```bash
./gather_component_context.py hypershift \
  --keywords "certificate" "custom" "TLS" \
  --max-prs 15 \
  --deep-dive 5 \
  -o hypershift-cert-context.md \
  -v
```

### Example 1b: Same as above, but always include upstream analysis

```bash
./gather_component_context.py hypershift \
  --keywords "certificate" "custom" "TLS" \
  --analyze-upstream \
  -o hypershift-cert-context.md \
  -v
```

### Example 2: Analyze multiple components for multi-component RFE

```bash
./gather_component_context.py \
  hypershift \
  cert-manager \
  cluster-ingress-operator \
  --keywords "certificate rotation" \
  -o multi-component-context.md
```

### Example 3: Get JSON for custom processing

```bash
./gather_component_context.py cert-manager \
  --keywords "ACME" \
  --json \
  -o cert-manager.json

# Process with jq
cat cert-manager.json | jq '.pr_insights[0].pr.title'
```

## Development

### Adding New Analysis Features

1. **Repository analysis**: Extend `github_repo_analyzer.py`
2. **PR analysis**: Extend `github_pr_analyzer.py`
3. **Output format**: Extend `context_synthesizer.py`
4. **Orchestration**: Modify `gather_component_context.py`

### Testing

```bash
# Test repo analyzer
python3 github_repo_analyzer.py cert-manager

# Test PR analyzer
python3 github_pr_analyzer.py openshift/cert-manager-operator certificate

# Test end-to-end
python3 gather_component_context.py cert-manager --keywords "test" -v
```

## See Also

- `../SKILL.md` - Full analyze-rfe implementation guide
- `../SETUP.md` - Jira setup instructions
- `fetch_rfe.py` - Jira RFE fetching script
