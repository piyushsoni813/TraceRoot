```edit
FILE: src/filelock/_api.py
<<<<<<< SEARCH
    def __call__(self, *args, **kwargs):
        init_params = {}
        if args:
            init_params['lock_file'] = args[0]
        if len(args) > 1:
            raise TypeError(
                f"{self._cls.__name__}.__init__() got an unexpected "
                f"keyword argument '{args[1]}'"
            )
        return super().__call__(**init_params)
=======
    def __call__(self, *args, **kwargs):
        init_params = {}
        if args:
            init_params['lock_file'] = args[0]
        if len(args) > 1:
            raise TypeError(
                f"{self._cls.__name__}.__init__() got an unexpected "
                f"keyword argument '{args[1]}'"
            )
        return super().__call__(**init_params)
>>>>>>> REPLACE
```