# Flask application construction fails for a direct script

Creating a Flask application in a Python script fails before the development
server starts. The same pattern previously worked. The failure occurs while the
framework determines the application's instance path.

Environment reported by the original reporter:

- Python 3.11.4
- Flask development branch

Expected behavior: constructing the application should succeed and the script
should be able to continue to its server startup code.
