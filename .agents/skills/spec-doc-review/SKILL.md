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
  - If the doc is "superseded" and "replacement" documents are named, do those documents exist?
- Does the frontmatter include a "description" field?
  - A required field for all spec docs: a one-sentence summary of what the document covers. Flag a missing description as a concern.
- Does the document have an "Open questions" section with unanswered questions?
  - This is acceptable in the "proposed" state. For any other state, flag this as suspicious, unless all
    questions are clearly marked as resolved/answered.
- If the document specifically supersedes another document, is that document marked as "superseded" with this document as the replacement?
- If the document has an "Additional dependencies" section, are the new dependencies clearly listed, with specific versions?
- If the document has a "Dependency changes" section, are the changes clearly specified?

## Advanced checks

- If proposing a new feature or a major refactor, is the proposal feasible?
  - Example: specifies a test that requires real network access or real wall-clock timing violates our hermetic test suite. Not feasible.
  - Example: has a hard requirement on a dependency that conflicts with our *exactly-pinned* dependencies. Not feasible.
- Does the document clearly specify what is to be implemented?
  - If it mentions error handling, are the specific error types mentioned?
  - Are the error cases clearly specified?
- Is the proposed design optimal? Does the doc propose an elaborate custom design that could be done much more easily with a built-in library function, for example?
- Does the spec doc introduce new configuration properties for the game ("Configuration" section)?
  - Are they named?
  - Is the new top-level configuration key named? Does it conflict with any known existing top-level key names?
  - Are the expected value(s) clearly defined?
  - Does the document specify a sensible default value to be used if the game config file is missing?
- Does the document describe specific test cases ("Testing" section)?
- Does the document have sensible acceptance criteria ("Acceptance criteria" section)? Are they clear and achievable? The section is optional per `docs/README.md`: if missing, criteria are inferred from the Testing section — verify the Testing section is strong enough to carry that weight.
- Does the document contradict itself?
- Does the document contradict other existing spec docs (that aren't marked as "superseded")? A documented 'Amendments to previous spec docs' section is expected drift, not a contradiction, until stage 1 of the dev plan is complete.
- If the document has an "Amendments to previous spec docs" section, does it also have a "Dev plan" section?
  Does the Dev plan explicitly mention carrying out the amendments as stage 1?
- Does the document have a "Dev plan" section? Fine if missing for small docs, but more than 250 lines of specification requires a staged implementation plan, unless the document is already in `active` state.
- Does the document introduce or alter third-party dependencies? If so, does it carry the corresponding 'Additional dependencies'/'Dependency changes' section, consistent with the exact pins in requirements.txt?

## The most important question to answer

If you were given this specification document to implement, would you have enough information
to provide a solid and well-tested implementation for it? If not, list what is missing in the document
that would allow you to succeed. If there are alternative design approaches that might be better,
suggest them. If the suggested design approach might cause problems later on, flag it.

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
The exception to this rule is if the user explicitly asks you to apply changes 
to the document (example: "Your suggestions sound good to me. Please update the spec doc with them.")

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
  
