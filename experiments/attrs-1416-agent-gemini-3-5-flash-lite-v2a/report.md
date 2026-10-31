# Investigation report: attrs-1416

Model: gemini-3.5-flash-lite. Tool calls: 31. Time: 145.0 s. Tokens: 381861.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/attr/_make.py`
- Function: `_transform_attrs`
- Breaking commit: `not identified`

When a generator function is passed as a `field_transformer`, it returns a generator iterator. Previously, `attrs = field_transformer(cls, attrs)` assigned the generator directly to `attrs`. When `attrs` was iterated multiple times (or first consumed when checking attribute orders / converting to `AttrsClass` / collecting base attributes by subclasses), the generator iterator was exhausted, resulting in empty attributes and unexpected initialization errors. Wrapping the result of `field_transformer` in `list(...)` ensures that generator-based field transformers can be iterated safely multiple times.

## Hypotheses

### H1 (supported)

H1: When field_transformer returns a list of attributes, what happens to AttrsClass / Base.__attrs_attrs__? Wait, Base.__attrs_attrs__ above printed `Base attrs: ()`! Why did it print `()`? Because `AttrsClass(attrs)` was called with `attrs` being empty or something? Wait, no, `attrs` in `_transform_attrs` was empty or `field_transformer` yielded nothing? Wait, in my test snippet above, `_all_after_dag_id_to_kw_only` yielded `f` and then `f.evolve(...)`. Why did `Base.__attrs_attrs__` evaluate to `()`?

- Predicts: If Base.__attrs_attrs__ is a subclass of tuple created by _make_attr_tuple_class, when Subclass inherits from Base, _collect_base_attrs iterates over Base.__attrs_attrs__ and checks `a.inherited`. Wait, why are attrs empty or missing? Let's check what `Base.__attrs_attrs__` actually contains!
- Evidence: Confirmed H1/H2: generator yielded by generator function `_all_after_dag_id_to_kw_only` is consumed by `AttrsClass(attrs)` (or earlier checks), leaving `attrs` empty when Base is finalized or when inherited. (tool calls 18, 19)

### H2 (supported)

H2: A generator function yields an iterator, which when passed to `AttrsClass(attrs)` (a tuple subclass) or similar, gets consumed or behaves unexpectedly because generators can only be iterated once or `_make_attr_tuple_class` expects a sized sequence/list. Wait, previously how was `field_transformer` handled? Let's check git history of `_transform_attrs`.

- Predicts: If `field_transformer` returns a generator or iterator instead of a list, `AttrsClass(attrs)` consumes the iterator or fails because an iterator is not a sequence / tuple or gets consumed once. `_make_attr_tuple_class` or `AttrsClass` expects a sequence, but `field_transformer` returned a generator function (which returns a generator iterator), and `AttrsClass(attrs)` consumes the generator or iterates over it, and then what? Wait, `AttrsClass` is a tuple subclass. `TupleClass(generator)` creates an empty tuple if not careful, or raises, or consumes it. Wait! Let's check how `AttrsClass` (created by `_make_attr_tuple_class`) handles iterators/generators!
- Evidence: Passing a generator (iterator) to AttrsClass (a tuple subclass) consumes the generator on the first call (when Base is created), leaving it empty for subsequent uses or if inspected/iterated again. Also, `field_transformer` docs state it returns a list or iterable of Attributes. But `AttrsClass(attrs)` consumes `attrs` if it's a generator! Wait, let's check what `_transform_attrs` does with `attrs`. (tool calls 18, 19)

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

- Call 27: `python reproducer snippet`: Subclass(dag_id='foo', has_default='default', other=False)
- Call 28: `pytest tests/test_hooks.py`: 13 passed in 0.06s
- Call 29: `pytest tests/test_make.py`: 262 passed, 1 skipped in 4.69s

## Evidence

### Call 18: run_python

Arguments: `{"code": "import attrs\n\ndef my_transformer(cls, fields):\n    return list(fields)\n\n@attrs.define(field_transformer=my_transformer)\nclass Base:\n    dag_id: str\n    has_default: str = \"default\"\n\nprint(\"Base attrs with list:\", Base.__attrs_attrs__)\n"}`

```
[exit 0]
Base attrs with list: (Attribute(name='dag_id', default=NOTHING, validator=None, repr=True, eq=True, eq_key=None, order=True, order_key=None, hash=None, init=True, metadata=mappingproxy({}), type=<class 'str'>, converter=None, kw_only=False, inherited=False, on_setattr=None, alias='dag_id'), Attribute(name='has_default', default='default', validator=None, repr=True, eq=True, eq_key=None, 
```

### Call 19: run_python

Arguments: `{"code": "gen = (x for x in [1, 2, 3])\nclass MyTuple(tuple):\n    pass\n\nt = MyTuple(gen)\nprint(t)\nt2 = MyTuple(gen)\nprint(t2)\n"}`

```
[exit 0]
(1, 2, 3)
()

```

### Call 27: apply_edit

Arguments: `{"search": "    if field_transformer is not None:\n        attrs = field_transformer(cls, attrs)", "path": "src/attr/_make.py", "replace": "    if field_transformer is not None:\n        attrs = list(field_transformer(cls, attrs))"}`

```
applied edit 1 to src/attr/_make.py. Run tests to check it.
```

### Call 28: run_python

Arguments: `{"code": "import attrs\n\ndef _all_after_dag_id_to_kw_only(cls, fields):\n    i = iter(fields)\n    f = next(i)\n    if f.name != \"dag_id\":\n        raise RuntimeError(\"dag_id was not the first field\")\n    yield f\n    for f in i:\n        yield f.evolve(kw_only=True)\n\n@attrs.define(field_tra`

```
[exit 0]
Subclass(dag_id='foo', has_default='default', other=False)

```

### Call 29: run_tests

Arguments: `{"selection": ["tests/test_hooks.py"]}`

```
[exit 0]
.............                                                            [100%]
13 passed in 0.06s

```

## Limitations

