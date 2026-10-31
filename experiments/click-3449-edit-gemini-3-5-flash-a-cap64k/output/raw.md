```edit
FILE: src/click/_termui_impl.py
<<<<<<< SEARCH
    if not isatty(sys.stdout):
        buffer = io.TextIOWrapper(stdout, encoding=get_best_encoding(stdout))

        for text in generator:
            buffer.write(text)

        buffer.flush()
        return
=======
    if not isatty(sys.stdout):
        buffer = io.TextIOWrapper(stdout, encoding=get_best_encoding(stdout))

        for text in generator:
            buffer.write(text)

        buffer.flush()
        buffer.detach()
        return
>>>>>>> REPLACE
```