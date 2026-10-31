"""Evaluator-only reproduction derived from python-attrs/attrs issue 1416. Exit 0 means fixed."""
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
