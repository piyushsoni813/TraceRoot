```edit
FILE: src/flask/scaffold.py
<<<<<<< SEARCH
    # we were unable to find the `package_path` using PEP 451 loaders
    spec = importlib.util.find_spec(root_mod_name)
    loader = spec.loader if spec is not None else None
=======
    # we were unable to find the `package_path` using PEP 451 loaders
    try:
        spec = importlib.util.find_spec(root_mod_name)
        loader = spec.loader if spec is not None else None
    except (ImportError, ValueError):
        loader = None
>>>>>>> REPLACE
```