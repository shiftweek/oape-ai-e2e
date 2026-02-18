# Historic PR Analysis in analyze-rfe

## Overview

The `analyze-rfe` skill now **automatically analyzes historic PRs** from downstream, upstream, and operand repositories to provide comprehensive context for RFE implementation planning.

## What Gets Analyzed

### 1. Downstream Repository (Always)
- **Example**: For RFE-5035 (cert-manager), analyzes `openshift/cert-manager-operator`
- **Searches for**: PRs related to RFE keywords (e.g., "instance", "auto-create", "GitOps")
- **Extracts**:
  - Design decisions and rationale
  - Implementation patterns
  - Architecture Decision Records (ADRs)
  - Lessons learned from similar features
  - Code complexity metrics (files changed, scope)

### 2. Upstream Repository (Optional, but recommended)
- **Example**: For cert-manager, analyzes `cert-manager/cert-manager`
- **Purpose**: Understand original design intent, find upstream features to adopt
- **When useful**:
  - Adopting upstream features
  - Understanding architectural differences
  - Planning contributions back to upstream

### 3. Operand Repositories (If component is an operator)
- **Example**: For `cluster-monitoring-operator`, analyzes `prometheus`, `alertmanager`, etc.
- **Purpose**: Understand where to implement RFE (operator lifecycle vs operand functionality)
- **Discovery**: Automatic from README, manifests, OLM metadata

## How It Works

### Step-by-Step Process

1. **Extract Component Names** from RFE Jira issue (components field + description)
2. **Extract Keywords** from RFE summary, description, desired behavior
3. **For each component**, run:
   ```bash
   python3 plugins/oape/skills/analyze-rfe/scripts/gather_component_context.py cert-manager \
     --keywords "instance" "auto-create" "GitOps" \
     --max-prs 50 \
     --deep-dive 3 \
     --analyze-upstream \
     --analyze-operands \
     -o .work/jira/analyze-rfe/RFE-5035/component-cert-manager-context.md
   ```

4. **Script performs**:
   - Repository discovery (downstream, upstream, operands)
   - Codebase structure analysis (architecture, CRDs, controllers)
   - PR search using keywords (title, body, comments)
   - Relevance ranking (more keyword matches = higher relevance)
   - Deep analysis of top 3 PRs (extract design sections, rationale)
   - ADR discovery (Architecture Decision Records)
   - Lessons learned extraction
   - Effort estimation (based on files changed, complexity)

5. **Output includes**:
   - Repository structure and architecture
   - Key implementation patterns from PRs
   - Relevant historic PRs with design insights
   - Upstream vs downstream comparison
   - Risk factors and mitigations
   - Recommended implementation approach

## Example Output

For RFE-5035 (cert-manager instance creation), the analysis would include:

```markdown
### Component: cert-manager

**Repositories**:
- Downstream: openshift/cert-manager-operator
- Upstream: cert-manager/cert-manager

**Architecture**: Kubernetes Operator (controller-runtime)

**Key Implementation Patterns** (from historic PRs):
1. **Operator Lifecycle Management** (PR #234): CSV-based configuration for operator behavior
2. **GitOps Compatibility** (PR #156): Annotation-based feature flags for declarative workflows

**Relevant Historic PRs**:
- **PR #234** (2024-03): Add CSV configuration for default instance creation
  - **Design Insight**: Used CSV annotations to control operator behavior without code changes
  - **Scope**: M (8 files changed)
  - **Relevance**: Similar pattern can be used for auto-create flag

- **PR #156** (2023-11): Support GitOps-managed CertManager instances
  - **Design Insight**: Added annotation `cert-manager.openshift.io/managed-by` to detect GitOps control
  - **Scope**: S (3 files changed)
  - **Relevance**: Existing GitOps detection logic can be extended

**Upstream vs Downstream**:
- Upstream has no operator lifecycle (pure Kubernetes operator)
- Downstream adds OpenShift-specific OLM integration
- Auto-creation is downstream-only behavior (not in upstream)

**Risk Factors**:
- **Backward Compatibility**: Changing default behavior may break existing workflows
  - **Mitigation**: Feature flag with default preserving current behavior
- **OLM Constraints**: CSV annotations have limited expressiveness
  - **Mitigation**: Start with env var, migrate to CRD config later

**Recommended Implementation Approach**:
1. Review PR #234 for CSV configuration pattern
2. Add environment variable `AUTO_CREATE_INSTANCE` (default: true)
3. Update operator reconciliation logic to check flag before creating default instance
4. Add E2E tests for both auto-create modes (see PR #156 for GitOps test patterns)
5. Document migration path for users switching to manual creation
```

## Configuration

### Command-Line Flags

When running `gather_component_context.py`:

| Flag | Purpose | Default |
|------|---------|---------|
| `--keywords` | RFE keywords for PR search | [] |
| `--max-prs` | Max PRs to search | 50 |
| `--deep-dive` | PRs to analyze in detail | 3 |
| `--analyze-upstream` | Always analyze upstream | Prompt user |
| `--skip-upstream` | Never analyze upstream | Prompt user |
| `--analyze-operands` | Always analyze operands | Prompt user |
| `--skip-operands` | Never analyze operands | Prompt user |
| `--no-interactive` | Skip all prompts | false |
| `--cache-dir` | Cache directory | `.work/jira/analyze-rfe/cache` |
| `-o` | Output file | stdout |
| `--json` | JSON output instead of markdown | false |
| `-v, --verbose` | Verbose logging | false |

### Environment Variables

```bash
# Optional overrides
export ANALYZE_RFE_MAX_PRS=100        # More PRs to search
export ANALYZE_RFE_DEEP_DIVE_PRS=5    # More detailed analysis
export ANALYZE_RFE_CACHE_DIR=/tmp/cache
```

## Prerequisites

### Required
- **GitHub CLI (`gh`)**: Install from https://cli.github.com/
- **Authenticated**: Run `gh auth login`

### Verify Setup
```bash
gh auth status
# Should show: ✓ Logged in to github.com as <username>
```

## Performance

### Typical Times
- Single component (no upstream, no operands): **5-10 seconds**
- Single component (with upstream): **15-30 seconds**
- Single component (operator with 3 operands): **45-90 seconds**

### Optimization
- **Caching**: Results cached to `.work/jira/analyze-rfe/cache/`
- **Subsequent runs**: <5 seconds (reads from cache)
- **Rate limits**: GitHub API allows 5000 req/hour (rarely hit)

## Cache Management

### Cache Structure
```
.work/jira/analyze-rfe/cache/
├── search_prs_openshift_cert-manager-operator_instance.json
├── pr_view_openshift_cert-manager-operator_234.json
├── repo_view_openshift_cert-manager-operator.json
└── repo_contents_openshift_cert-manager-operator_api.json
```

### Clear Cache
```bash
# Clear all caches
rm -rf .work/jira/analyze-rfe/cache/

# Clear cache for specific component
rm -rf .work/jira/analyze-rfe/cache/*cert-manager*
```

## Troubleshooting

### "gh: command not found"
```bash
# macOS
brew install gh

# Fedora/RHEL
sudo dnf install gh

# Ubuntu/Debian
sudo apt install gh

# Then authenticate
gh auth login
```

### "No PRs found"
- **Check keywords**: Use specific terms from RFE, not generic words
- **Example**: Instead of "certificate", use "certificate rotation" or "ACME"
- **Verify repo**: Ensure repository name is correct in component mapping

### "Analysis incomplete"
- **GitHub API timeout**: Increase timeout or reduce `--max-prs`
- **Rate limit**: Wait an hour or use cached results
- **Network issue**: Check internet connection

### PRs not relevant
- **Refine keywords**: Extract more specific terms from RFE
- **Increase max-prs**: `--max-prs 100` to search more PRs
- **Check upstream**: Relevant PRs might be in upstream repo

## Integration with analyze-rfe Skill

The historic PR analysis is now **Step 3 (required)** in `SKILL.md`:

```python
# Pseudo-code for analyze-rfe implementation
rfe_data = fetch_rfe("RFE-5035")
components = extract_components(rfe_data)  # ["cert-manager"]
keywords = extract_keywords(rfe_data)      # ["instance", "auto-create", "GitOps"]

for component in components:
    context = gather_component_context(
        component,
        keywords=keywords,
        max_prs=50,
        deep_dive=3,
        analyze_upstream=True,    # Always analyze upstream
        analyze_operands=True,    # Always analyze operands (if operator)
    )

    # Use context in EPIC and story generation
    generate_epics(rfe_data, context)
    generate_user_stories(rfe_data, context)
```

## Best Practices

### 1. Good Keyword Selection
✅ **Good**: `["auto-create", "default instance", "GitOps", "declarative"]`
❌ **Bad**: `["instance", "create", "operator"]` (too generic)

### 2. Upstream Analysis
- **Always analyze** for upstream adoption RFEs
- **Skip** for OpenShift-only features with no upstream equivalent

### 3. Operand Analysis
- **Always analyze** if RFE mentions operand functionality
- **Example**: "Add Prometheus feature" → analyze prometheus operand
- **Skip** if RFE is pure operator lifecycle (installation, upgrades)

### 4. Cache Management
- **Keep cache** during active RFE analysis (speeds up iterations)
- **Clear cache** when switching to different RFEs or components
- **Check cache size** periodically (`du -sh .work/jira/analyze-rfe/cache`)

## Output Format

### Markdown (default)
- Structured markdown per component
- Includes repos, patterns, PRs, risks, recommendations
- Ready to paste into RFE breakdown

### JSON (programmatic)
```bash
gather_component_context.py cert-manager --json -o output.json

# Process with jq
cat output.json | jq '.pr_insights[0].pr.title'
cat output.json | jq '.structure.architecture'
```

## See Also

- **SKILL.md**: Full analyze-rfe implementation guide
- **scripts/README.md**: Detailed script documentation
- **OPERATOR_OPERAND_ANALYSIS.md**: Operator-operand analysis guide
- **GitHub PR Analyzer**: `scripts/github_pr_analyzer.py`
- **Repo Analyzer**: `scripts/github_repo_analyzer.py`
- **Operand Discovery**: `scripts/operand_discovery.py`
