---
name: trellis-check
description: "Comprehensive quality verification: spec compliance, lint, type-check, tests, cross-layer data flow, code reuse, and consistency checks. Use when code is written and needs quality verification, before committing changes, or to catch context drift during long sessions."
---

# Code Quality Check

Comprehensive quality verification for recently written code. Combines spec compliance, cross-layer safety, and pre-commit checks.

---

## Step 1: Identify What Changed

```bash
git diff --name-only HEAD
git status
```

## Step 2: Read Applicable Specs

```bash
python3 ./.trellis/scripts/get_context.py --mode packages
```

For each changed package/layer, read the spec index and follow its **Quality Check** section:

```bash
cat .trellis/spec/<package>/<layer>/index.md
```

Read the specific guideline files referenced — the index is a pointer, not the goal.

## Step 3: Run Project Checks

Run the project's lint, type-check, and test commands. Fix any failures before proceeding.

## Step 4: Review Against Checklist

### Code Quality

- [ ] **[Error]** Linter passes?
- [ ] **[Error]** Type checker passes (if applicable)?
- [ ] **[Error]** Tests pass?
- [ ] **[Error]** No debug logging left in?
- [ ] **[Error]** No suppressed warnings or type-safety bypasses?

### Test Coverage

- [ ] **[Warning]** New function → unit test added?
- [ ] **[Warning]** Bug fix → regression test added?
- [ ] **[Warning]** Changed behavior → existing tests updated?

### Spec Sync

- [ ] **[Info]** Does `.trellis/spec/` need updates? (new patterns, conventions, lessons learned)

> "If I fixed a bug or discovered something non-obvious, should I document it so future me won't hit the same issue?" → If YES, update the relevant spec doc.

## Step 5: Cross-Layer Dimensions (if applicable)

Skip this step if your change is confined to a single layer.

### A. Data Flow (changes touch 3+ layers)

- [ ] **[Warning]** Read flow traces correctly: Storage → Service → API → UI
- [ ] **[Warning]** Write flow traces correctly: UI → API → Service → Storage
- [ ] **[Warning]** Types/schemas correctly passed between layers?
- [ ] **[Warning]** Errors properly propagated to caller?

### B. Code Reuse (modifying constants, creating utilities)

- [ ] **[Warning]** Searched for existing similar code before creating new?
  ```bash
  grep -r "pattern" src/
  ```
- [ ] **[Warning]** If 2+ places define same value → extracted to shared constant?
- [ ] **[Warning]** After batch modification, all occurrences updated?

### C. Import/Dependency (creating new files)

- [ ] **[Warning]** Correct import paths (relative vs absolute)?
- [ ] **[Warning]** No circular dependencies?

### D. Same-Layer Consistency

- [ ] **[Warning]** Other places using the same concept are consistent?

## Step 5b: Severity Handling

- **Error**: Must fix before check passes. Re-run verification after fix.
- **Warning**: Should fix but not blocking. Record in report.
- **Info**: Informational. Record in report.

If any Error-level issues remain unfixed, the check FAILS.
If only Warning/Info issues remain, the check PASSES with notes.

---

## Step 6: Report and Fix

Report violations found and fix them directly. Re-run project checks after fixes.

Group findings by severity (Errors → Warnings → Info) in the report.
