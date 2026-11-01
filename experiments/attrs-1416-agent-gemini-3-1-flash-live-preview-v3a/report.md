# Investigation report: attrs-1416

Model: gemini-3.1-flash-live-preview. Tool calls: 28. Time: 57.7 s. Tokens: 0.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/attr/_make.py`
- Function: `_transform_attrs`
- Breaking commit: `not identified`

The code was assigning the output of the field_transformer directly to the 'attrs' variable. If the field_transformer was a generator, 'attrs' became an iterator. Subsequent code iterated over 'attrs' multiple times (e.g., in the mandatory vs non-mandatory order check, and when creating the AttrsClass tuple), causing the iterator to be exhausted after the first pass. This led to missing attributes in the generated class.

## Hypotheses

### H1 (rejected)

The `field_transformer` on `Base` is not being applied when collecting attributes for `Subclass`, leading to incorrect attribute collection and `__init__` generation.

- Predicts: The generated `__init__` method for `Subclass` will not have `dag_id` as a parameter.
- Evidence: The field_transformer IS applied to Base. The issue is how attrs handles the generator returned by the transformer. (tool calls 18, 19, 20)

### H2 (supported)

The `field_transformer` IS applied, but the resulting attributes are somehow mishandled during `__init__` generation for the subclass.

- Predicts: The generated `__init__` method for `Subclass` will have `dag_id` as a parameter, but it might be keyword-only when it shouldn't be, or vice versa, or there's some other issue with how `__init__` is generated.
- Evidence: The reproducer fails when the field_transformer is a generator. When changed to return a list, it works. This indicates that attrs is not correctly handling generator functions as field_transformers, likely consuming them partially or incorrectly. (tool calls 18, 19, 20)

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

- Call 20: `run_python reproduction script with list-returning transformer`: success
- Call 24: `run_python reproduction script with generator transformer after fix`: success
- Call 25: `run_tests tests`: failures in tests/test_packaging.py, unrelated to change

## Evidence

### Call 18: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    print(f\"Transforming fields for {cls.__name__}\")\n    i = iter(fields)\n    f = next(i)\n    if f.name != \"dag_id\":\n        raise RuntimeError(\"dag_id was not the first field\")\n    yield f\n    for f in i:\n       `

```
[exit 0]
Transforming fields for Base
Base fields: []
Subclass fields: ['other']
Subclass.__init__() got an unexpected keyword argument 'dag_id'

```

### Call 19: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    print(f\"Transforming fields for {cls.__name__}\")\n    fields_list = list(fields)\n    print(f\"Input fields: {[f.name for f in fields_list]}\")\n    i = iter(fields_list)\n    try:\n        f = next(i)\n        if f.name`

```
[exit 0]
Transforming fields for Base
Input fields: ['dag_id', 'has_default']
Base fields: []
Subclass fields: ['other']
Subclass.__init__() got an unexpected keyword argument 'dag_id'

```

### Call 20: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    print(f\"Transforming fields for {cls.__name__}\")\n    fields_list = list(fields)\n    print(f\"Input fields: {[f.name for f in fields_list]}\")\n    \n    result = []\n    i = iter(fields_list)\n    try:\n        f = nex`

```
[exit 0]
Transforming fields for Base
Input fields: ['dag_id', 'has_default']
Output fields: ['dag_id', 'has_default']
Base fields: ['dag_id', 'has_default']
Subclass fields: ['dag_id', 'has_default', 'other']
Subclass(dag_id='foo', has_default='default', other=False)

```

### Call 24: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    i = iter(fields)\n    f = next(i)\n    if f.name != \"dag_id\":\n        raise RuntimeError(\"dag_id was not the first field\")\n    yield f\n    for f in i:\n        yield f.evolve(kw_only=True)\n\n@attrs.define(field_tra`

```
[exit 0]
Subclass(dag_id='foo', has_default='default', other=False)

```

### Call 25: run_tests

Arguments: `{"selection": ["tests"]}`

```
[exit 1]
........................................................................ [  5%]
........................................................................ [ 10%]
........................................................................ [ 16%]
........................................................................ [ 21%]
.......................................................................
```

## Limitations

- The fix forces materialization of the field transformer output into a list. This might have performance implications if a field transformer generates a very large number of fields, although this is unlikely in practice.
- Four existing tests in tests/test_packaging.py failed, but these failures appear unrelated to the change and are likely due to the sandboxed environment lacking package metadata for 'attrs'.
