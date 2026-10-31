```edit
FILE: src/click/testing.py
<<<<<<< SEARCH
                sys.stdout.flush()
                sys.stderr.flush()
=======
                try:
                    sys.stdout.flush()
                except ValueError:
                    pass
                try:
                    sys.stderr.flush()
                except ValueError:
                    pass
>>>>>>> REPLACE
```