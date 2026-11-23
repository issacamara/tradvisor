---
name: factory-software-design-patterns
description: Recommend and apply a suitable software design pattern or a simpler existing solution for a concrete design problem.
---

# Software Design Patterns

Read the behavior, callers, and conventions first. Name the actual change pressure or failure. Compare the simplest option (direct call, conditional, existing helper) against any pattern.

## When to use a pattern

Use a pattern only when at least one holds:

- The same change is needed in three or more places.
- Two or more real variants exist now. Hypothetical variants do not count.
- You must integrate an interface you do not control.
- A cross-cutting concern (logging, retry, auth, caching) wraps many operations.
- A concrete bug or untestable design traces back to the structure.

Otherwise keep the simple version: one implementation, a stable conditional with two or three branches, a helper that only forwards, or a one-off script.

## Catalog

| Pressure | Pattern | Simpler alternative |
|---|---|---|
| Interchangeable behavior chosen at runtime | Strategy | Function parameter or dict of functions |
| Behavior changes with lifecycle state | State | Status enum with a transition table |
| Fixed sequence, varying steps, duplicated | Template Method | Shared function taking the steps as arguments |
| Object family chosen by input or config | Factory | Constructor or function returning the class |
| Many optional parameters or invariants | Builder | Keyword arguments with defaults |
| Foreign interface you cannot change | Adapter | Direct call if both sides are yours |
| Same multi-step call repeated by 3+ callers | Facade | One helper function |
| Same wrapping applied to many operations | Decorator | Explicit shared call |
| Storage may change or needs a test fake | Repository | Direct queries in a small data layer |
| Independent reactions; publisher should not know them | Observer / Pub-Sub | Direct call to the one known caller |
| Queue, retry, audit, or undo as data | Command | Direct function call |
| Ordered handlers that may stop or pass on | Chain of Responsibility / Pipeline | Sequential calls |

## Avoid

- Singleton for mutable global state. Inject the dependency instead.
- Observer with one caller. Call it directly.
- Abstract Factory with one type. Use a constructor.
- Any pattern added "for future flexibility." Remove it.

## Output

Each recommendation states:

1. The change pressure or failure, with the files and call sites that show it.
2. The simpler alternative and why it was accepted or rejected.
3. The chosen pattern and the complexity it adds.
4. A codebase-adapted example, with callers and tests updated.
5. Validation evidence and limitations.
