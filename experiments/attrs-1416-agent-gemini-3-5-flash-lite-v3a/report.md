# Investigation report: attrs-1416

Model: gemini-3.5-flash-lite. Tool calls: 22. Time: 95.0 s. Tokens: 208267.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/attr/_make.py`
- Function: `_transform_attrs`
- Breaking commit: `not identified`

When a field_transformer returned an iterator or generator (which is single-pass), attrs iterated over it multiple times for order validation, alias resolution, and constructing AttrsClass, exhausting the iterator/generator on the first iteration. Converting the result of field_transformer to a list ensures that it can be iterated multiple times safely.

## Hypotheses

### H1 (supported)

The field_transformer function in the user code returns a generator (from `yield`), but `AttrsClass(attrs)` or `_transform_attrs` expects a list or sequence (or `attrs` is used multiple times / exhausted if it's an iterator/generator).

- Predicts: If generator function is exhausted when `AttrsClass(attrs)` is called or when fields are iterated, or if `field_transformer` modifies/returns an iterator instead of a list, `attrs` becomes empty or doesn't work as expected.
- Evidence: Wrapping generator return value with list(...) in field_transformer makes Base attrs and Subclass attrs populate correctly and instantiation succeed. (tool calls 13)

### H2 (supported)

`field_transformer` can return any iterable (including a generator), but attrs code expects a collection/list and might iterate over it multiple times or pass a generator object directly to `AttrsClass(...)` or check operations on it.

- Predicts: Converting `field_transformer` return value to list via `list(field_transformer(...))` or handling iterables/iterators robustly fixes the issue when `field_transformer` returns a generator.
- Evidence: When field_transformer returns a generator (which is an iterable but single-pass), attrs uses it multiple times (e.g. for order check, alias resolution, and AttrsClass(attrs)), exhausting it on the first use. Converting attrs to list (or list(field_transformer(...))) ensures it can be iterated multiple times. (tool calls 13)

## Patch

```diff
diff --git a/src/attr/_make.py b/src/attr/_make.py
index 7439dc2..41bc412 100644
--- a/src/attr/_make.py
+++ b/src/attr/_make.py
@@ -448,7 +448,7 @@ def _transform_attrs(
     attrs = base_attrs + own_attrs
 
     if field_transformer is not None:
-        attrs = field_transformer(cls, attrs)
+        attrs = list(field_transformer(cls, attrs))
 
     # Check attr order after executing the field_transformer.
     # Mandatory vs non-mandatory attr order only matters when they are part of
```

## Verification

- Call 20: `python script with reproducer`: Subclass(dag_id='foo', has_default='default', other=False)\nSuccess!
- Call 21: `pytest tests/test_hooks.py tests/test_make.py`: 275 passed, 1 skipped in 4.82s

## Evidence

### Call 13: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    i = iter(fields)\n    f = next(i)\n    if f.name != \"dag_id\":\n        raise RuntimeError(\"dag_id was not the first field\")\n    yield f\n    for f in i:\n        yield f.evolve(kw_only=True)\n\n@attrs.define(field_tra`

```
[exit 0]
Base attrs: (Attribute(name='dag_id', default=NOTHING, validator=None, repr=True, eq=True, eq_key=None, order=True, order_key=None, hash=None, init=True, metadata=mappingproxy({}), type=<class 'str'>, converter=None, kw_only=False, inherited=False, on_setattr=None, alias='dag_id'), Attribute(name='has_default', default='default', validator=None, repr=True, eq=True, eq_key=None, order=True
```

### Call 20: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    i = iter(fields)\n    f = next(i)\n    if f.name != \"dag_id\":\n        raise RuntimeError(\"dag_id was not the first field\")\n    yield f\n    for f in i:\n        yield f.evolve(kw_only=True)\n\n@attrs.define(field_tra`

```
[exit 0]
Subclass(dag_id='foo', has_default='default', other=False)
Success!

```

### Call 21: run_tests

Arguments: `{"selection": ["tests/test_hooks.py", "tests/test_make.py"]}`

```
[exit 0]
........................................................................ [ 26%]
........................................................................ [ 52%]
........................................................................ [ 78%]
....................................................s.......             [100%]
=========================== short test summary info ===================
```

## Limitations

