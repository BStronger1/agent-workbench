# Action targets

- A contract `data-testid` names one actionable element, never a repeated list or a group. Preserve the intended item's identity. Use classes or other attributes for group queries.
- For `check`, use a visible native checkbox/radio, a correctly implemented ARIA control, or its associated label. A surrounding card/div alone is not checkable. Bind state changes to the actual control; avoid double toggling when a click bubbles from input to card.
- For `fill`, target a real editable input/textarea or supported contenteditable element. Read its current value when the action runs, not a stale value captured at startup.
- A dynamically rendered element must still be unique at action time. If replacing a subtree, restore handlers or delegate them from a stable ancestor. A cloned/replaced node does not retain direct event listeners.
- Keep valid controls visible and enabled for the required action. Fix the app's prerequisite logic instead of forcing a click through overlays or disabling strict selector checks.
