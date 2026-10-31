# Investigation report: attrs-1416

Model: gemini-3.1-flash-live-preview. Tool calls: 31. Time: 72.2 s. Tokens: 0.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/attr/_make.py`
- Function: `_transform_attrs`
- Breaking commit: `not identified`

The `field_transformer` argument in `attrs.define` (and `attr.s`) allows a callable to transform the fields of a class. If this callable is a generator function, it returns an iterator. The code in `_transform_attrs` was using this iterator directly. However, the resulting `attrs` list was iterated over multiple times (e.g., to check order, resolve aliases, and create the attribute tuple class). The first iteration consumed the generator, leaving subsequent iterations empty. This led to incorrect class creation, especially for subclasses which would miss inherited attributes.

## Hypotheses

### H1 (rejected)

The `field_transformer` on `Base` modifies the fields, making `dag_id` positional and `has_default` keyword-only. When `Subclass` is defined, `_transform_attrs` collects `Base`'s fields. If `field_transformer` is NOT run on `Subclass`, it sees `dag_id` as positional. However, if `Subclass` also has fields, and `define()` defaults to `collect_by_mro=True`, the combination of inherited fields and new fields might be causing `dag_id` to be dropped from `__init__` arguments if it's not correctly handled during `__init__` generation. Specifically, if `dag_id` is somehow considered as not belonging to `Subclass`'s init signature.

- Predicts: If I modify the reproducer to print `Subclass.__init__.__annotations__`, I will see that `dag_id` is missing from the arguments.
- Evidence: The fix in `src/attr/_make.py` resolved the issue, confirming that the problem was related to how `field_transformer` output was handled, rather than `dag_id` being dropped due to MRO issues with new fields. (tool calls 22, 24)

### H2 (supported)

The `field_transformer` on `Base` works as expected. When `Subclass` is defined, it inherits attributes from `Base`. `_transform_attrs` calls `_collect_base_attrs`. If `_collect_base_attrs` somehow uses the *original* definitions of fields from `Base` instead of the transformed ones stored in `Base.__attrs_attrs__`, then `dag_id` would be positional. But the reproducer says `dag_id` is unexpected keyword argument. This means `dag_id` is NOT in `__init__` at all, or it is positional and we are passing it as keyword. Wait, `x = Subclass(dag_id="foo", other=False)` should work if `dag_id` is positional. The error is `unexpected keyword argument 'dag_id'`. This means `dag_id` is NOT in `__init__` signature.

Revised Hypothesis: The `field_transformer` on `Base` works. `Base.__init__` has `dag_id` (positional) and `has_default` (kw_only). When `Subclass` is defined, `_transform_attrs` collects base attributes. If `_collect_base_attrs` collects `dag_id` and `has_default`. And then `Subclass` adds `other`.

If `dag_id` is missing from `Subclass.__init__`, it means it was filtered out.

Let's look at `_collect_base_attrs` in `src/attr/_make.py`:
```python
324	    for base_cls in reversed(cls.__mro__[1:-1]):
325	        for a in getattr(base_cls, "__attrs_attrs__", []):
326	            if a.inherited or a.name in taken_attr_names:
327	                continue
328	
329	            a = a.evolve(inherited=True)  # noqa: PLW2901
330	            base_attrs.append(a)
```
It reads `__attrs_attrs__` from base classes. `Base.__attrs_attrs__` should contain transformed fields.

If `dag_id` is missing from `Subclass.__init__`, maybe it's because `Subclass` definition somehow overrides it? In reproducer:
```python
@attrs.define()
class Subclass(Base):
    other: bool
```
`other` is the only own attribute. `taken_attr_names` will be `{'other'}`. `dag_id` is not in `taken_attr_names`.

Maybe the issue is that `field_transformer` is NOT inherited, and `Subclass` definition process re-transforms fields in a way that drops `dag_id`? But `Subclass` doesn't have a `field_transformer`.

If `dag_id` is positional in `Subclass`, `Subclass(dag_id="foo", other=False)` should work.

If `dag_id` is keyword-only in `Subclass`, `Subclass(dag_id="foo", other=False)` should work.

The error `TypeError: Subclass.__init__() got an unexpected keyword argument 'dag_id'` strongly suggests `dag_id` is not in the signature.

Why would `dag_id` be missing?

Maybe `Base` is not considered an attrs class when `Subclass` is being built?

Let's check what `Base.__attrs_attrs__` contains.

- Predicts: If I modify the reproducer to print `Base.__attrs_attrs__` and `Subclass.__attrs_attrs__`, I will see that `dag_id` has `kw_only=True` in `Subclass` but `kw_only=False` in `Base`.
- Evidence: The reproducer fails as described. Investigation showed that when `field_transformer` is a generator, it is iterated over multiple times. The first iteration consumes it, leaving subsequent iterations empty. This causes `Base` to have no attributes, and `Subclass` to only have its own attributes, missing inherited ones. Converting the generator output to a list in `src/attr/_make.py` fixes the issue in the reproducer. (tool calls 2, 18, 19, 20, 21, 22, 24)

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

- Call 2: `run_python reproducer.py`: TypeError: Subclass.__init__() got an unexpected keyword argument 'dag_id'
- Call 24: `run_python reproducer.py`: Subclass(dag_id='foo', has_default='default', other=False)
- Call 27: `run_tests tests/test_make.py`: 262 passed, 1 skipped
- Call 28: `run_tests tests/test_next_gen.py`: 33 passed

## Evidence

### Call 2: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    i = iter(fields)\n    f = next(i)\n    if f.name != \"dag_id\":\n        raise RuntimeError(\"dag_id was not the first field\")\n    yield f\n    for f in i:\n        yield f.evolve(kw_only=True)\n\n@attrs.define(field_tra`

```
[exit 0]
Subclass.__init__() got an unexpected keyword argument 'dag_id'

```

### Call 18: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    i = iter(fields)\n    f = next(i)\n    if f.name != \"dag_id\":\n        raise RuntimeError(\"dag_id was not the first field\")\n    yield f\n    for f in i:\n        yield f.evolve(kw_only=True)\n\n@attrs.define(field_tra`

```
[exit 1]
Base fields: []
Traceback (most recent call last):
  File "<string>", line 22, in <module>
    print(f"Base dag_id kw_only: {Base.__attrs_attrs__[0].kw_only}")
                                  ~~~~~~~~~~~~~~~~~~~~^^^
IndexError: tuple index out of range

```

### Call 19: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    print(f\"Transforming fields for {cls.__name__}\")\n    i = iter(fields)\n    try:\n        f = next(i)\n    except StopIteration:\n        return fields\n        \n    if f.name != \"dag_id\":\n        # raise RuntimeErro`

```
[exit 0]
Transforming fields for Base
Base fields: []
Subclass fields: ['other']
Subclass dag_id kw_only: False
Subclass init signature: (other: bool) -> None

```

### Call 20: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    print(f\"Transforming fields for {cls.__name__}\")\n    fields_list = list(fields)\n    print(f\"Input fields: {[f.name for f in fields_list]}\")\n    \n    i = iter(fields_list)\n    try:\n        f = next(i)\n    except `

```
[exit 0]
Transforming fields for Base
Input fields: ['dag_id', 'has_default']
Base fields: []
Subclass fields: ['other']
Subclass dag_id kw_only: False
Subclass init signature: (other: bool) -> None

```

### Call 21: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    print(f\"Transforming fields for {cls.__name__}\")\n    fields_list = list(fields)\n    print(f\"Input fields: {[f.name for f in fields_list]}\")\n    \n    def generator():\n        i = iter(fields_list)\n        try:\n  `

```
[exit 0]
Transforming fields for Base
Input fields: ['dag_id', 'has_default']
Base fields: []
Subclass fields: ['other']
Subclass dag_id kw_only: False
Subclass init signature: (other: bool) -> None

```

### Call 22: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    print(f\"Transforming fields for {cls.__name__}\")\n    fields_list = list(fields)\n    print(f\"Input fields: {[f.name for f in fields_list]}\")\n    \n    result = []\n    i = iter(fields_list)\n    try:\n        f = nex`

```
[exit 0]
Transforming fields for Base
Input fields: ['dag_id', 'has_default']
Base fields: ['dag_id', 'has_default']
Base dag_id kw_only: False
Base has_default kw_only: True
Subclass fields: ['dag_id', 'has_default', 'other']
Subclass dag_id kw_only: False
Subclass init signature: (dag_id: str, other: bool, *, has_default: str = 'default') -> None
Subclass(dag_id='foo', has_default='default', oth
```

### Call 24: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    i = iter(fields)\n    f = next(i)\n    if f.name != \"dag_id\":\n        raise RuntimeError(\"dag_id was not the first field\")\n    yield f\n    for f in i:\n        yield f.evolve(kw_only=True)\n\n@attrs.define(field_tra`

```
[exit 0]
Subclass(dag_id='foo', has_default='default', other=False)

```

### Call 27: run_tests

Arguments: `{"selection": ["tests/test_make.py"]}`

```
[exit 0]
........................................................................ [ 27%]
........................................................................ [ 54%]
........................................................................ [ 82%]
.......................................s.......                          [100%]
=========================== short test summary info ===================
```

### Call 28: run_tests

Arguments: `{"selection": ["tests/test_next_gen.py"]}`

```
[exit 0]
.................................                                        [100%]
33 passed in 0.24s

```

## Limitations

- Some tests in tests/test_packaging.py failed, but these failures seem unrelated to the change and are likely due to the test environment lacking package metadata for 'attrs'. Existing tests related to class creation (test_make.py, test_next_gen.py) passed.
