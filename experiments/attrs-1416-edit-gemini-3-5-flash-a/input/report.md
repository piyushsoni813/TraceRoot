Creating an instance of a subclass fails with an unexpected-keyword error. The same
code worked in the previous release.

A base class uses `field_transformer` to make every field after `dag_id` keyword-only.
The field transformer is a generator function. A subclass of that base class then
fails when it is instantiated with the `dag_id` keyword.

Minimal reproducer:

```python
import attrs

def _all_after_dag_id_to_kw_only(cls, fields):
    i = iter(fields)
    f = next(i)
    if f.name != "dag_id":
        raise RuntimeError("dag_id was not the first field")
    yield f
    for f in i:
        yield f.evolve(kw_only=True)

@attrs.define(field_transformer=_all_after_dag_id_to_kw_only)
class Base:
    dag_id: str
    has_default: str = "default"

@attrs.define()
class Subclass(Base):
    other: bool

x = Subclass(dag_id="foo", other=False)
print(repr(x))
```

Expected behavior: the instance is created and printed.
