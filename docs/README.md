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
