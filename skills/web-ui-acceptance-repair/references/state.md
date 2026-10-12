# State repair

- Replay the complete ordered contract, including intermediate assertions and repeated inputs/clicks.
- Read current .value/.checked properties rather than initial attributes or stale captures. Convert numeric inputs before addition.
- Preserve state independently of filtered or re-rendered DOM. Count the task's intended items, not hidden templates or unrelated controls.
- innerHTML replacement destroys direct listeners. Rebind/delegate handlers; avoid duplicate bubbling handlers.
- Keep results visible and self-contained. The browser blocks network and form submissions. Preserve initial state for assert_changed.
