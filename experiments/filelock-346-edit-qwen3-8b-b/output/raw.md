```edit
FILE: src/filelock/_api.py
<<<<<<< SEARCH
        all_params = {
            "lock_file": lock_file,
            "timeout": timeout,
            "mode": mode,
            "thread_local": thread_local,
            "blocking": blocking,
            "is_singleton": is_singleton,
            **kwargs,
        }
=======
        all_params = {
            "lock_file": lock_file,
            "timeout": timeout,
            "mode": mode,
            "thread_local": thread_local,
            "blocking": blocking,
            "is_singleton": is_singleton,
            **kwargs,
        }
        # Ensure 'lock_file' is passed as a keyword argument to avoid positional argument issues
        if 'lock_file' in all_params:
            all_params.pop('lock_file')
            all_params['lock_file'] = lock_file
>>>>>>> REPLACE
```