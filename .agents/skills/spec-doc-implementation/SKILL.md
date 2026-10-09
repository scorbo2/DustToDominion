---
name: spec-doc-implementation
description: Use when the user wants to implement a specification doc that has passed review.
---

# Implementing a specification doc

Once a spec doc has been reviewed and approved, implementation can begin. If a "Dev plan"
section is present, implementation will proceed one discrete stage at a time.

## Scenario one: there is no dev plan

In the absence of a "Dev plan" section with a staged implementation plan, consider the
entire document and approach it as methodically as you can. The task is to implement
the entire contents of the document.

## Scenario two: a dev plan is present

We will implement ONE stage at a time.

At the completion of each stage, add a completion marker to the stage description
with the current date in `yyyy-MM-dd` format.

Example of a stage to be implemented:

```
- Create the `Foobar` class with stubbed-out accessor functions.
  The class should log a message when it is constructed, but all other
  functions should be a no-op.
```

Upon successful completion, mark the stage as complete:

```
- Create the `Foobar` class with stubbed-out accessor functions.
  The class should log a message when it is constructed, but all other
  functions should be a no-op. **Completed 2026-05-28**
```

If the user did not specify which stage to implement, assume that we are implementing
the first stage that is not explicitly marked as completed. If all stages are already
marked as completed, run the Final completion step (flip to active, reword prose,
remove the Amendments section) unless the user says otherwise.

## Final completion step

Flipping the document from `proposed` to `active` status should not happen until
implementation is fully complete with all tests passing. All acceptance criteria (if any
are listed) should be met. If no acceptance criteria are listed, we will rely on the
test suite results as the sole indicator of success.

After marking the document as `active`, update the prose in the document to reword
"proposes" to "describes", to reflect the new state of the document. Examples:
- "This document proposes..." -> change to "This document describes..."
- "The Foobar class, when implemented, will handle this." -> change to "The Foobar class handles this."

If the document had an "Amendments to previous spec docs" section, and those amendments
were successfully carried out during implementation, then update the document to remove
that section. There's no need to keep the description of proposed amendments here once they
have been carried out - it's just noise. If the document listed specific test descriptions
associated with those amendments, move those test descriptions to the "Testing" section
of the amended doc. This helps keep every spec doc more tightly focused.

If the spec doc has an "Open questions" section, and not all questions are clearly
marked as resolved/answered, the document cannot be flipped to `active` state.
Leave the doc in `proposed` state and flag this for the user's attention.
Do not mark questions as resolved or answered yourself - only the user may do that. 

