# Ordered interaction and state

- Walk through every contract step in order, including repeated clicks/fills and assertions between them. A repair must satisfy all intermediate states, not only the last expected string.
- Read live input values and checkbox `.checked` properties when the action runs. HTML attributes describe initial state; `.value` and `.checked` describe current state. Handle numeric conversion explicitly to avoid string concatenation.
- Keep application state separate from presentation. Derive counts/results from current task state; do not count hidden template nodes, unrelated checkboxes, or only the currently filtered DOM when the task calls for all items.
- Updating a list with `innerHTML` destroys direct listeners on old nodes. Rebind after render or use delegation on a stable ancestor. Avoid both input and parent click handlers toggling the same item.
- A valid result must become visible and update after the required action. `assert_text` compares trimmed `textContent` exactly, so extra nested labels also contribute. Place decorative labels outside the result element.
- `assert_changed` compares against the value before the contract's actions. Preserve meaningful initial state, and compute the updated result from user input. Do not prefill the expected answer just to satisfy an assertion.
- Keep local interactions self-contained; the browser blocks network requests and form submission. A button handler must finish the operation within this environment.
