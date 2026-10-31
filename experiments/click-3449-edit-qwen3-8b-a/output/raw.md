```edit
FILE: src/click/testing.py
<<<<<<< SEARCH
        sys.stdout.flush()
=======
        if sys.stdout is not None:
            sys.stdout.flush()
>>>>>>> REPLACE
```