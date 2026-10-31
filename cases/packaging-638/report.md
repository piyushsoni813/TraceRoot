Evaluating a marker that mentions `extra` raises a TypeError when the environment
passes `extra` as `None`. This used to return `False`.

```python
from packaging.markers import Marker

marker = Marker('extra == "opt-feature"')
print(marker.evaluate({"extra": None}))
```

Expected behavior: `False` is printed. Existing callers pass `None` for `extra`
when no extra is being evaluated.
