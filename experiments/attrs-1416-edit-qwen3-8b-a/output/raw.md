```edit
FILE: src/example/module.py
<<<<<<< SEARCH
def _all_after_dag_id_to_kw_only(cls, fields):
    i = iter(fields)
    f = next(i)
    if f.name != "dag_id":
        raise RuntimeError("dag_id was not the first field")
    yield f
    for f in i:
        yield f.evolve(kw_only=True)
=======
def _all_after_dag_id_to_kw_only(cls, fields):
    i = iter(fields)
    f = next(i)
    if f.name != "dag_id":
        raise RuntimeError("dag_id was not the first field")
    yield f
    for f in i:
        yield f.evolve(kw_only=True)
    yield f.evolve(kw_only=True)
>>>>>>> REPLACE
```