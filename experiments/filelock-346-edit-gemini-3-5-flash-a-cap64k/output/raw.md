```edit
FILE: src/filelock/_api.py
<<<<<<< SEARCH
        instance = super().__call__(**init_params)
=======
        instance = super().__call__(*args, **kwargs)
>>>>>>> REPLACE
```