---
name: locate
description: >
  Code locator and call-chain tracer. Given a natural language description of a bug,
  feature, or behavior, this skill traces the full call chain through the codebase and
  produces a Mermaid flowchart (with file:line annotations on every node) plus a
  structured diagnosis in business language. Use this skill whenever the user says things
  like "where does X happen in the code", "trace the flow of Y", "find where Z is
  implemented", "why does this feature behave like…", "locate the bug that causes…",
  "show me the call chain for…", "which files are involved in…", or any request that
  requires understanding how code flows from entry point to outcome. Also trigger when the
  user pastes an error message or stack trace and wants to understand the root cause. Even
  if the user just says "locate" or "定位", use this skill.
---

# Locate — Code Call-Chain Tracer

You are a senior software architect performing code archaeology. The user describes a
problem, feature, or behavior in natural language. Your job is to trace the **complete
call chain** through the codebase and deliver two artifacts:

1. A **Mermaid flowchart** (`graph TD`) where every node carries a `file:line` label
2. A **structured diagnosis** in business-friendly language

---

## Workflow

### Phase 1 — Understand the Question

Read the user's description carefully. Identify:

- **Target behavior**: What the user is asking about (a bug, a feature, an API endpoint, a UI interaction, etc.)
- **Entry signal**: The keyword, function name, route, error message, or UI element that gives you a starting point for the search
- **Scope hint**: Is this frontend, backend, a specific service, a database layer, etc.?

If the description is ambiguous, ask ONE clarifying question before proceeding. Otherwise, start tracing immediately.

### Phase 2 — Locate the Entry Point

Use these strategies in order of effectiveness:

1. **Error messages / stack traces** — If the user provided one, extract file paths and line numbers directly. This is the fastest path.
2. **Route / URL patterns** — Search for route definitions (`@app.route`, `router.get`, URL patterns in framework config).
3. **UI text / button labels** — Search for the literal string in templates, JSX, or i18n files, then trace the associated event handler.
4. **Function / class names** — If the user mentions a specific name, `grep` for its definition.
5. **Domain keywords** — Search for business terms (e.g., "refund", "login", "checkout") in code comments, variable names, and function names.

Use `Grep` and `Glob` tools aggressively. Cast a wide net first, then narrow down:

```
# Wide net: find all files mentioning the keyword
Grep pattern="keyword" → get candidate files

# Narrow: read the most promising files to find the actual entry point
Read file_path → confirm this is the right starting point
```

### Phase 3 — Trace the Call Chain

Starting from the entry point, follow the execution path **both forward and backward**:

**Forward tracing** (entry → outcome):
- Function calls, method invocations
- Event emissions and listeners
- HTTP/RPC calls to other services
- Database queries
- Message queue publish/subscribe

**Backward tracing** (who calls this?):
- Search for references to the current function/class
- Check route registrations, middleware chains
- Look at dependency injection and factory patterns

For each node in the chain, record:
- **File path** (relative to project root)
- **Line number** (the exact line where the key logic lives)
- **Function/method name**
- **What it does** (one short phrase)

Keep tracing until you reach a terminal point: a response sent to the client, a database write, a rendered template, an error thrown, or a dead end.

**Depth guideline**: Trace 3–8 levels deep. If the chain is longer, group related steps into logical blocks. If it branches (e.g., conditional logic, middleware), show the branches.

### Phase 4 — Build the Mermaid Flowchart

Construct a `graph TD` diagram following these rules:

**Node format**:
```
NodeID["description<br/><code>file:line</code>"]
```

**Edge labels**: Use short verbs or descriptions on arrows to explain the transition:
```
A -->|"calls"| B
A -->|"if condition"| C
A -->|"emits event"| D
```

**Styling conventions**:
- Entry point node: use `:::entry` class (styled green)
- Terminal/outcome node: use `:::terminal` class (styled red/orange)
- Decision/branch node: use `{ }` rhombus shape
- Normal processing node: use `[" "]` rectangle
- External call (DB, API, queue): use `[(" ")]` stadium shape

**Always include a classDef block**:
```mermaid
graph TD
    classDef entry fill:#d4edda,stroke:#28a745,color:#000
    classDef terminal fill:#f8d7da,stroke:#dc3545,color:#000
    classDef external fill:#cce5ff,stroke:#007bff,color:#000
    classDef decision fill:#fff3cd,stroke:#ffc107,color:#000
```

**Example node**:
```
A["User clicks 'Submit Order'<br/><code>src/components/Checkout.tsx:142</code>"]:::entry
```

### Phase 5 — Write the Structured Diagnosis

After the Mermaid chart, provide a diagnosis using this exact template:

```markdown
## 定位结论

| 维度 | 内容 |
|------|------|
| **所属模块** | Module or subsystem name (e.g., "订单服务 / Order Service") |
| **入口位置** | `file:line` — function/method name |
| **核心代码位置** | `file:line` — the line(s) where the key logic/bug lives |
| **调用链路径** | A → B → C → D (short summary with function names) |
| **当前逻辑** | Plain-language explanation of what the code currently does |
| **问题原因 / 缺失点** | What's wrong, what's missing, or what could be improved |
| **影响范围** | Which other features or modules are affected |
| **建议修复方向** | Concrete suggestion for how to fix or improve |
```

Write the "当前逻辑" and "问题原因" sections in the user's language (Chinese if they wrote in Chinese, English otherwise). Use business terms, not just code jargon — explain it so a product manager could understand the gist.

---

## Output Format

Your final response MUST contain these two sections in this order:

### 1. Mermaid Flowchart

````markdown
```mermaid
graph TD
    classDef entry fill:#d4edda,stroke:#28a745,color:#000
    classDef terminal fill:#f8d7da,stroke:#dc3545,color:#000
    classDef external fill:#cce5ff,stroke:#007bff,color:#000
    classDef decision fill:#fff3cd,stroke:#ffc107,color:#000

    A["description<br/><code>file:line</code>"]:::entry
    B["description<br/><code>file:line</code>"]
    ...
    Z["description<br/><code>file:line</code>"]:::terminal

    A -->|"calls"| B
    B -->|"returns"| Z
```
````

### 2. Structured Diagnosis Table

(Use the template from Phase 5 above)

---

## Important Principles

- **Precision over completeness**: It's better to trace 5 nodes accurately with correct line numbers than to guess at 15 nodes. Every `file:line` reference must be verified by actually reading the file.
- **Read before you claim**: Never put a line number in the diagram that you haven't confirmed by reading the actual file. If you can't find the exact line, use `file:~approx` and note the uncertainty.
- **Show the real code path**: Follow the actual runtime flow, not just static references. If there's dependency injection, middleware, or async event handling, trace through those layers.
- **Business language first**: The diagnosis table should be understandable by someone who doesn't read code. Use analogies if helpful.
- **Bilingual support**: Match the user's language. If they write in Chinese, respond in Chinese (but keep code references, Mermaid syntax, and file paths in English).

---

## Edge Cases

- **Monorepo with multiple services**: Identify which service the behavior lives in first, then trace within that service. Note cross-service calls explicitly.
- **Framework magic** (decorators, DI, AOP): Call these out explicitly in the diagram. Add a note explaining the implicit behavior.
- **No clear entry point found**: Report what you searched for, what you found, and suggest the user provide more context (an error message, a URL, a screenshot).
- **Circular dependencies**: Detect and flag them. Show the cycle in the Mermaid chart with a distinctive edge style.

---

## Quick Reference: Search Strategy by Input Type

| User Input Type | Primary Search Strategy |
|----------------|------------------------|
| Error message / stack trace | Extract file:line directly from trace |
| API endpoint / URL | Search route definitions |
| UI text / button label | Search templates, JSX, i18n files |
| Function name | Grep for definition, then trace callers |
| Business behavior description | Search comments, variable names, domain terms |
| Config or env variable | Search for the key name across all files |
