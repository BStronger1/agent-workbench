# Target repair

- Keep the intended item's identity; a test ID identifies one element. Group queries should use classes.
- A check target is a native checkbox/radio, functional ARIA control or associated label. Move the attribute from a wrapper to its control when needed. Avoid toggling twice through event bubbling.
- A fill target must be editable. Read its current value on action.
- After replacing DOM nodes, rebind listeners or delegate from a stable ancestor. Keep controls visible and enabled.
