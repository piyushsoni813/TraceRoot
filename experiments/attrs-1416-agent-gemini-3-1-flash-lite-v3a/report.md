# Investigation report: attrs-1416

Model: gemini-3.1-flash-lite. Tool calls: 40. Time: 229.4 s. Tokens: 338413.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/attr/_make.py`
- Function: `_ClassBuilder (indirectly)`
- Breaking commit: `not identified`

The field_transformer was allowed to return a generator, which was exhausted when attrs processed the fields. Converting the result of the field_transformer to a list ensures it can be iterated multiple times.

## Hypotheses

### H1 (supported)

The field_transformer is incorrectly modifying the fields in a way that breaks the subclass's ability to accept the base class's fields in its __init__. Specifically, it might be marking fields as kw_only that should not be, or it's not correctly handling the inheritance of fields.

- Predicts: If the field_transformer is causing the issue, then removing it or changing it to not set kw_only=True should fix the issue. If the issue is in how attrs handles inheritance with field_transformer, then the issue will persist even if I change the field_transformer.
- Evidence: The issue is that the field_transformer was a generator, and attrs was consuming it in a way that resulted in empty fields for the base class. When I changed it to return a list, it worked correctly. This suggests that attrs expects the field_transformer to return a list, or at least not a generator that gets exhausted prematurely. Wait, if I pass a generator to attrs, it should be able to iterate over it. Let me check how attrs handles the field_transformer. (tool calls 20, 21, 23, 24, 25)

### H2 (rejected)

The issue is not the field_transformer itself, but how attrs handles inheritance when the base class has kw_only fields. The field_transformer is just a way to trigger this behavior.

- Predicts: If the issue is in how attrs handles inheritance, then even without a field_transformer, the subclass might have issues if the base class has kw_only fields. I will test this by creating a base class with kw_only=True without a field_transformer.
- Evidence: The subclass works fine when the base class has kw_only=True without a field_transformer. This suggests the issue is specific to how field_transformer interacts with the fields. (tool calls 18)

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

- Call 31: `python3 reproduce.py`: Subclass(dag_id='foo', has_default='default', other=False)
- Call 39: `pytest tests/test_make.py`: 262 passed, 1 skipped in 3.63s

## Evidence

### Call 18: run_python

Arguments: `{"code": "import attrs\n\n@attrs.define(kw_only=True)\nclass Base:\n    dag_id: str\n    has_default: str = \"default\"\n\n@attrs.define()\nclass Subclass(Base):\n    other: bool\n\ntry:\n    x = Subclass(dag_id=\"foo\", other=False)\n    print(repr(x))\nexcept Exception as e:\n    print(e)\n"}`

```
[exit 0]
Subclass(dag_id='foo', has_default='default', other=False)

```

### Call 20: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    i = iter(fields)\n    f = next(i)\n    if f.name != \"dag_id\":\n        raise RuntimeError(\"dag_id was not the first field\")\n    yield f\n    for f in i:\n        yield f.evolve(kw_only=True)\n\n@attrs.define(field_tra`

```
[exit 0]
Base fields: ()
Subclass fields: (Attribute(name='other', default=NOTHING, validator=None, repr=True, eq=True, eq_key=None, order=True, order_key=None, hash=None, init=True, metadata=mappingproxy({}), type=<class 'bool'>, converter=None, kw_only=False, inherited=False, on_setattr=None, alias='other'),)

```

### Call 21: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    i = iter(fields)\n    f = next(i)\n    if f.name != \"dag_id\":\n        raise RuntimeError(\"dag_id was not the first field\")\n    yield f\n    for f in i:\n        yield f.evolve(kw_only=True)\n\n@attrs.define(field_tra`

```
[exit 0]
Base fields: ()

```

### Call 23: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    # Just return the fields as is\n    return fields\n\n@attrs.define(field_transformer=_all_after_dag_id_to_kw_only)\nclass Base:\n    dag_id: str\n    has_default: str = \"default\"\n\nprint(f\"Base fields: {attrs.fields(Ba`

```
[exit 0]
Base fields: (Attribute(name='dag_id', default=NOTHING, validator=None, repr=True, eq=True, eq_key=None, order=True, order_key=None, hash=None, init=True, metadata=mappingproxy({}), type=<class 'str'>, converter=None, kw_only=False, inherited=False, on_setattr=None, alias='dag_id'), Attribute(name='has_default', default='default', validator=None, repr=True, eq=True, eq_key=None, order=Tru
```

### Call 24: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    # Return a list instead of a generator\n    i = iter(fields)\n    f = next(i)\n    res = [f]\n    for f in i:\n        res.append(f.evolve(kw_only=True))\n    return res\n\n@attrs.define(field_transformer=_all_after_dag_id`

```
[exit 0]
Base fields: (Attribute(name='dag_id', default=NOTHING, validator=None, repr=True, eq=True, eq_key=None, order=True, order_key=None, hash=None, init=True, metadata=mappingproxy({}), type=<class 'str'>, converter=None, kw_only=False, inherited=False, on_setattr=None, alias='dag_id'), Attribute(name='has_default', default='default', validator=None, repr=True, eq=True, eq_key=None, order=Tru
```

### Call 25: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    # Return a list instead of a generator\n    i = iter(fields)\n    f = next(i)\n    res = [f]\n    for f in i:\n        res.append(f.evolve(kw_only=True))\n    return res\n\n@attrs.define(field_transformer=_all_after_dag_id`

```
[exit 0]
Subclass(dag_id='foo', has_default='default', other=False)

```

### Call 31: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    i = iter(fields)\n    f = next(i)\n    if f.name != \"dag_id\":\n        raise RuntimeError(\"dag_id was not the first field\")\n    yield f\n    for f in i:\n        yield f.evolve(kw_only=True)\n\n@attrs.define(field_tra`

```
[exit 0]
Subclass(dag_id='foo', has_default='default', other=False)

```

### Call 39: run_tests

Arguments: `{"selection": ["tests/test_make.py"]}`

```
[exit 0]
........................................................................ [ 27%]
........................................................................ [ 54%]
........................................................................ [ 82%]
.......................................s.......                          [100%]
=========================== short test summary info ===================
```

## Limitations

- The tests failed due to environment issues (missing package metadata for 'attrs'), not because of the fix. I verified the fix with the provided reproducer and by running the relevant test file (tests/test_make.py).
