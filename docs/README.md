# Docs

Architecture documents for the project go here.

This is an entirely **spec-driven project**.

For every new feature:
- The human develops the spec
- The LLM reviews the spec and helps refine it
- The LLM writes the code

For changes to existing code:
- The human updates the spec and/or adds a new spec that supersedes an older one
- The LLM reviews the spec changes and helps refine them
- The LLM adjusts the code

For bug fixes:
- The human and the LLM review the spec to see if changes are warranted.
- Very simple bug fixes might require no spec changes.
- Larger bug fixes may involve amendments to one or more spec docs.

**The spec should always be up-to-date with the code, unless the spec is explicitly marked as superseded.**

## Document format

Each architecture document's name starts with a number indicating its creation order. The rest of the name
should briefly describe the document contents.

Example: `00-project-overview.md`

All documents are in Markdown format with Yaml frontmatter. Every spec document's frontmatter must include
a `description` field: a one-sentence summary of what the document covers, so that the spec set can be
scanned quickly without opening each document. The frontmatter also contains a `status` field with
these possible values:

- `proposed`: the document has not yet been implemented.
- `active`: the document has been implemented and reflects the current state of the code.
- `superseded`: the document has fallen out of date since implementation, or was never implemented. An additional
  Yaml field called `replacement` contains the name of the document(s) which supersede this one.
  The `replacement` field is optional.

If the frontmatter section of a document is missing, the document is assumed to be in `proposed` state.

When a document moves from `proposed` to `active`, its prose must be updated to match: an implemented
document *describes* (or *specifies*) what the code does - it no longer "proposes" it. Stale
"proposes"/"proposed" wording in an `active` document is a spec/code-sync drift like any other, and
the whole spec set should be checked for it when a feature is completed.

Note that the `00-project-overview.md` document does not have Yaml frontmatter, as it is the only
specification document that is not intended to produce runnable code - it is a guideline document.

### Example of a superseded document

Superseded by a specific named document:

```
---
description: Purchase and handover of new ships for the player's fleet.
status: superseded
replacement: 09-new-ship-handling.md
---
```

Superseded by multiple named documents:

```
---
description: Purchase and handover of new ships for the player's fleet.
status: superseded
replacement:
  - 09-new-ship-handling.md
  - 10-fleet-management.md
---
```

Superseded without a named document is also allowable:

```
---
description: Purchase and handover of new ships for the player's fleet.
status: superseded
---
```

## Mandatory sections

If the document introduces a new third-party dependency, it must have an "Additional dependencies"
section that clearly lists each new dependency and its version to be pinned.

If the document changes or removes any existing third-party dependency it must have
a "Dependency changes" section clearly describing the change.

If the document is too complicated to be implemented in a single pass, it must have a
"Dev plan" section with a stage-by-stage implementation breakdown. "Too complicated" is
subjective and sometimes non-obvious, so we will use a document line count of 250 lines
as a determiner (total lines in the spec doc, including frontmatter). A spec doc that
has more than 250 lines of text requires a dev plan when the document is in the `proposed`
state (already `active` documents are exempted). Note: it is not an error to include a
dev plan even for short or uncomplicated spec docs.

If a document has an "Amendments to previous spec docs" section, it must have a dev plan,
and the first stage in the dev plan MUST be to implement the amendments (see Amending
spec docs).

Each spec doc must have a `Testing` section that clearly describes what the unit tests
for the code in question should cover.

## Strongly recommended sections

Each spec doc *should* have a `Configuration` section that clearly describes any configuration
properties used by the code in question, along with their default values.

Each spec *should* have an `Acceptance criteria` section with a bullet list of specific
criteria that can be tested in order to determine whether or not the spec has been correctly
and completely implemented. If this section is missing, then acceptance criteria for the
doc can be inferred from the "Testing" section.

## Open questions

Documents in the `proposed` state may have an `Open questions` section with a list of
questions that should be addressed before implementation. **These questions must be addressed
before moving to `active`!**

It is acceptable to leave the "Open questions" section in the document, IF all questions have
an answer clearly documented (for future reference purposes).

## Amending spec docs

### Amending via another spec doc

New spec docs may require changes to previous, active spec docs. This is acceptable, as long
as the changes are clearly defined:
- what must change?
- why must it change?
- are new tests required? The Testing section must describe them.

If this section is present, then the "Dev plan" section becomes mandatory. Additionally,
the first stage of the dev plan must be to implement the amendments to previous spec docs.

The amended document is updated in place and retains its current status; once the amendments
are carried out, the 'Amendments' section is removed from the amending document.

### Amending directly

If an active spec doc requires changes that are NOT driven from some other spec doc, but rather
due to a desire to change the behavior of the doc in question, then the following general flow
should be followed:
- flip the doc from `active` back to `proposed` to indicate that there is work to be done.
- modify the doc: remove deprecated behavior, add new behavior, modify existing behavior, etc.
- if a Dev plan section was present, add at least one new stage to cover the changes.
  If the changes are too large to implement in a single stage, add several stages.
  The final stage should include instructions to flip the doc back to `active` status.
  The added stages should include wording to make it clear that these stages were added
  *after* initial implementation. Include the current date. For example: "Amendment 2026-05-29".
- if a Dev plan section was not present, add one, unless the change is trivial.
  A label/wording change, for example, does not warrant the creation of a Dev plan.

Any changes to behavior require changes to tests! If the previous behavior was untested, add tests!
Any new behavior requires new tests!
Deleting previous behavior may require deletion or modification of existing tests.

