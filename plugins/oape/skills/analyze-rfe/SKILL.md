---
name: Analyze RFE
description: Analyze RFEs and generate EPIC, user stories, and outcomes breakdown
---

# Analyze RFE

Implementation guidance for `/oape:analyze-rfe`. When invoked, execute the steps below.

## Prerequisites

- **Jira**: `JIRA_PERSONAL_TOKEN` set (and optionally `JIRA_URL`, default `https://issues.redhat.com`). If unset, prompt the user and exit.
- **Input**: RFE key (e.g. `RFE-7841`) or Jira URL. Extract key from URL if needed (e.g. `https://issues.redhat.com/browse/RFE-7841` → `RFE-7841`).
- **Optional (for Step 3 script-based context)**: GitHub CLI `gh` authenticated (`gh auth login`). Used by `gather_component_context.py` (which calls `github_pr_analyzer.py` and related scripts).

## Step 1: Fetch the RFE

1. Parse input: if it looks like a URL, extract the issue key; otherwise use as key.
2. Fetch the RFE:
   - **Preferred**: Run the script (from plugin root or skill dir):
     ```bash
     python3 plugins/oape/skills/analyze-rfe/scripts/fetch_rfe.py {issue_key}
     ```
     Script requires `JIRA_PERSONAL_TOKEN` and `pip install requests`. It prints JSON to stdout and clear errors to stderr.
   - **Alternative**: Use curl or Python requests:
     ```bash
     curl -sS -H "Authorization: Bearer $JIRA_PERSONAL_TOKEN" \
          -H "Accept: application/json" \
          "$JIRA_URL/rest/api/2/issue/{key}?fields=summary,description,components,labels,status,issuetype"
     ```
3. On 401/403/404: report clear error and exit. If token missing, show setup instructions (see script stderr or command doc).
4. Extract: key, summary, description, components, status, labels.

## Step 2: Parse RFE Content

From the description (strip Jira wiki markup), extract:
- **Nature/Description** — what is being requested
- **Current Limitation** — what doesn’t work today
- **Desired Behavior** — what should happen (bullets/paragraphs)
- **Use Case** — intended usage and scenarios
- **Business Requirements** — impact, justification
- **Affected Components** — teams, operators (from description and Jira components)

Note missing sections; still proceed with available content.

## Step 3: Gather Component Context and Historic PR Analysis (Required)

1. **Extract component names** from RFE (from Jira components field and description).
2. **Extract keywords** from RFE description, summary, and desired behavior for PR search.
3. **For each affected component**, run the component context gatherer with PR analysis:
   ```bash
   python3 plugins/oape/skills/analyze-rfe/scripts/gather_component_context.py <component-name> \
     --keywords "keyword1" "keyword2" "keyword3" \
     --max-prs 50 \
     --deep-dive 3 \
     --analyze-upstream \
     --analyze-operands \
     -o .work/jira/analyze-rfe/<rfe-key>/component-<component-name>-context.md
   ```

   **What this does**:
   - Discovers **downstream** repo (e.g., `openshift/cert-manager-operator`)
   - Discovers **upstream** repo (e.g., `cert-manager/cert-manager`)
   - Searches for relevant **PRs** using RFE keywords (checks title, body, comments)
   - Analyzes PR history for **design decisions**, **lessons learned**, **ADRs**
   - If component is an operator, discovers and analyzes **operand repos**
   - Caches results to `.work/jira/analyze-rfe/cache/` for performance

   **Prerequisites**: `gh` CLI authenticated (`gh auth login`). If `gh` is not available, log a warning and skip PR analysis (generate basic context only).

4. **Fallback**: Search workspace for `**/context.md` files if script-based analysis fails.
5. **Synthesize**: Merge PR insights, repo structure, and context.md data into the final report.
6. **Use in output**: Include "Component Context & Historical PR Analysis" section with:
   - What the component does, architecture pattern
   - Key implementation patterns from historic PRs
   - Relevant PRs with design rationale
   - Upstream vs downstream differences (if upstream analyzed)
   - Operand repos and their purpose (if operator)
   - Risk factors and recommended approach

## Step 4: Generate EPIC(s)

- **Count**: One epic for a single capability; 2–3 if clearly distinct (e.g. API + UI, or phased MVP then enhancements).
- **Per epic**: Summary/title, objective, scope (in/out), 3–6 acceptance criteria (outcome-focused), target users.
- Align with the RFE’s desired behavior and use case.

## Step 5: Generate User Stories

- **Format**: “As a &lt;role&gt;, I want to &lt;action&gt;, so that &lt;value&gt;.”
- **Per story**: User story text, short summary (5–10 words), 2–6 acceptance criteria (testable), outcome (value delivered).
- One story per distinct user-facing capability; right-size for one sprint.
- Map to desired behavior and (if present) workspace context key areas.

## Step 6: Define Outcomes

- For each story: 1–2 sentence outcome (business/value delivered).
- Add epic-level outcome summary.

## Step 7: Output the Report

1. Emit markdown in this structure:

```markdown
# RFE Analysis: [KEY] - [Title]

## RFE Summary
| Field | Value |
|-------|-------|
| **Source** | [link] |
| **Key Capability** | ... |
| **Business Driver** | ... |
| **Affected Components** | ... |

## Component Context & Historic PR Analysis

[For each affected component]

### Component: [Component Name]

**Repositories**:
- Downstream: openshift/[repo-name]
- Upstream: [upstream-org/repo-name] (if applicable)
- Operands: [operand repos] (if operator)

**Architecture**: [Operator/CLI/Library/Service]

**Key Implementation Patterns** (from historic PRs):
1. [Pattern 1 from PR analysis]
2. [Pattern 2 from PR analysis]

**Relevant Historic PRs**:
- **PR #[number]** ([date]): [Title]
  - **Design Insight**: [What was designed and why]
  - **Scope**: [S/M/L - files changed]
  - **Relevance**: [Why this matters for current RFE]

**Upstream vs Downstream** (if upstream analyzed):
- [Key differences in architecture, features, or approach]

**Risk Factors**:
- [Risks identified from PR analysis and codebase structure]
- **Mitigation**: [Recommendations]

**Recommended Implementation Approach**:
- [Based on historic patterns and lessons learned]

## EPIC(s)
### EPIC 1: [Title]
**Objective**: ...
**Scope**: In scope / Out of scope
**Acceptance Criteria**: ...

## User Stories
### Epic 1 → Story 1.1: [Title]
**User Story**: As a ... I want ... So that ...
**Acceptance Criteria**: ...
**Outcome**: ...

## Outcomes Summary
| Story | Outcome |
...
---
*Generated by `/oape:analyze-rfe` on [timestamp]*
```

2. Optionally write the same content to `.work/jira/analyze-rfe/<rfe-key>/breakdown.md` (create directory if needed).

## Error Handling

- **No token**: Explain how to create and set `JIRA_PERSONAL_TOKEN`; exit.
- **Issue not found**: Check key and permissions; exit.
- **Not RFE project**: Warn and continue.
- **Sparse RFE**: Note gaps; still produce best-effort breakdown.

## Best Practices

- Synthesize from the RFE; don’t copy-paste long blocks.
- Epics = quarter-sized; stories = sprint-sized.
- Every story has a clear outcome.
- When workspace context exists, use it to tighten scope and key areas.
