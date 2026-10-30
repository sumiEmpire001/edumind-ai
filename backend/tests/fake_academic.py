"""Deterministic fixture only; never imported by the production application."""

from app.ai.provider import Turn


class FixtureProvider:
    available = True
    mode = "verification"

    def __init__(self):
        self.calls = 0
        self.contexts: list[list[Turn]] = []

    async def generate(self, context: list[Turn]) -> str:
        self.calls += 1
        self.contexts.append(context)
        turns = sum(t.role == "user" for t in context)
        return (
            r"""This is a scripted verification response, not academic guidance.

### Worked example

1. **Known values:** mass = 2 kg; acceleration = 3 m/s².
2. **Formula:** $F = ma$.
3. **Substitution:** $F = 2 \times 3$.
4. **Example result:** **6 N**.

$$
F = ma = 6 \text{ N}
$$

| Quantity | Value |
| --- | --- |
| Mass | 2 kg |
| Acceleration | 3 m/s² |

```python
force = 2 * 3
print(force)
```

"""
            + f"Context contains {turns} user question(s)."
        )
