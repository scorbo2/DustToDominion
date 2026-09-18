---
name: spec-doc-review
description: Use when the user wants to review a new or modified specification document.
---

# Reviewing a specification document

This project is spec-driven. All new features or nontrivial refactorings/bug fixes must
be driven by a specification document. Reviewing these documents for viability and
suitability before implementation is very important.

## Basic checks

- Does the spec doc live in the `docs/` directory?
- Does it follow the `NN-short-description.md` naming pattern?
- Is `NN` unique?
  - If this is a new document, is "NN" the next unused number in the sequence of existing documents?
- Does the Yaml frontmatter exist at the top of the document?
  - It is not an error if this frontmatter is missing (default to "proposed" state), but flag it as a concern.
- Does it have a valid "status" tag? (proposed/active/superseded)
  - If "superseded" and a "replacement" document is named, does that document exist?
- Does the frontmatter include a "description" field?
  - A required field for all spec docs: a one-sentence summary of what the document covers. Flag a missing description as a concern.
- Does the document have an "Open questions" section with unanswered questions?
  - This is acceptable in the "proposed" state. For any other state, flag this as suspicious.
- If the document is in "active" state, does it match the actual code behavior?
- If the document specifically supersedes another document, is that document marked as "superseded" with this document as the replacement?

## Advanced checks

- If proposing a new feature or a major refactor, is the proposal feasible?
  - Example: specifies a test that requires real network access or real wall-clock timing violates our hermetic test suite. Not feasible.
  - Example: has a hard requirement on a dependency that conflicts with our *exactly-pinned* dependencies. Not feasible.
- Does the document clearly specify what is to be implemented?
  - If it mentions error handling, are the specific error types mentioned?
  - Are the error cases clearly specified?
- Does the spec doc introduce new configuration properties for the game ("Configuration" section)?
  - Are they named?
  - Is the new top-level configuration key named? Does it conflict with any known existing top-level key names?
  - Are the expected value(s) clearly defined?
  - Does the document specify a sensible default value to be used if the game config file is missing?
- Does the document describe specific test cases ("Testing" section)?
- Does the document have sensible acceptance criteria ("Acceptance criteria" section)?
- Does the document contradict itself?
- Does the document contradict other existing spec docs (that aren't marked as "superseded")?

## The most important question to answer

If you were given this specification document to implement, would you have enough information
to provide a solid and well-tested implementation for it? If not, list what is missing in the document
that would allow you to succeed.

## What NOT to do

We are NOT modifying the game's code during a spec doc review. We are NOT implementing the spec doc
until the user provides approval.

It is acceptable to write code to test the feasibility of an approach, or to verify specific behavior.
**Don't modify tracked files**. Run scratch scripts from outside the project directory with `PYTHONPATH`
set to the project's absolute directory + `src`, and `import dtd.*` read-only.

Never modify the actual `~/.DustToDominion/` directory contents. You can redirect this with
`DUST_TO_DOMINION_HOME` pointing to any temporary readable/writable directory.

Do NOT automatically apply your suggestions to the document! 
Your primary goal is to provide feedback on the document to the user.

## Review format

Your findings should quote specific sections and line numbers in the spec doc where possible.
Your review should be divided into the following sections:

- **Major problems**: proposal not feasible, critical information missing, blatant contradictions, etc.
- **Minor concerns**: vagueness in the document that may cause problems during implementation (judgement calls), or other document issues that may not be fatal, but should at least be flagged.
- **Open questions** (if the document has an "Open questions" section): offer your best suggested answers. If a question is very vague, you may offer multiple suggestions per question.
- **Spelling and grammar**: for spelling and grammatical mistakes.
- **Clarifications**: for any questions you have for the user regarding the document's contents or the document's intentions.
- **Final verdict**:
  - **Good to go**: the document is locked down tight and ready for implementation.
  - **Needs major rework**: the document cannot be implemented as written.
  - **Minor changes suggested**: the document could be implemented as written, but there are a few small points that could be tightened.
  
