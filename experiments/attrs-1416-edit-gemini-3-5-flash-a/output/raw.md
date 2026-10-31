```edit
FILE: src/attr/_make.py
<<<<<<< SEARCH
    if field_transformer is not None:
        fields = field_transformer(cls, fields)
=======
    if field_transformer is not None:
        fields = list(field_transformer(cls, fields))
>>>>>>> REPLACE
```