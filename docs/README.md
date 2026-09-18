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

**The spec should always be up-to-date with the code, unless the spec is explicitly marked as superseded/deprecated.**

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
  Yaml field called `replacement` contains the name of the document which supersedes this one.

If the frontmatter section of a document is missing, the document is assumed to be in `proposed` state.

Note that the `00-project-overview.md` document does not have Yaml frontmatter, as it is the only
specification document that is not intended to produce runnable code - it is a guideline document.

### Example of a superseded document

```
---
description: Purchase and handover of new ships for the player's fleet.
status: superseded
replacement: 09-new-ship-handling.md
---
```

## Strongly recommended sections

Each spec doc should have a `Configuration` section that clearly describes any configuration
properties used by the code in question, along with their default values.

Each spec doc should have a `Testing` section that clearly describes what the unit tests
for the code in question should cover.

Each spec should have an `Acceptance criteria` section with a bullet list of specific
criteria that can be tested in order to determine whether or not the spec has been correctly
and completely implemented.

## Open questions

Documents in the `proposed` state may have an `Open questions` section with a list of
questions that should be addressed before implementation. **These questions must be addressed
before moving to `active`!**

It is acceptable to leave the "Open questions" section in the document, IF all questions have
an answer clearly documented (for future reference purposes).

