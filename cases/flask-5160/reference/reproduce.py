"""Evaluator-only reproduction derived from Flask issue 5160.

Keep this file outside model input. The reported failure happens during
``Flask(__name__)`` construction; a server does not need to be started.
"""

from flask import Flask


app = Flask(__name__)
print(app.name)
