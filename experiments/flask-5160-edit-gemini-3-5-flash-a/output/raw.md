```edit
FILE: src/flask/scaffold.py
<<<<<<< SEARCH
    try:
        spec = importlib.util.find_spec(root_mod_name)
    except AttributeError:
        spec = None
=======
    try:
        spec = importlib.util.find_spec(root_mod_name)
    except (AttributeError, ValueError):
        spec = None
>>>>>>> REPLACE
```