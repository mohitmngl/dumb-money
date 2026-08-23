import sys
import os
from multiprocessing import freeze_support

if __name__ == "__main__":
    freeze_support()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    from dumbmoney.app import app, create_app

    create_app()
    app.run(host="0.0.0.0", port=8474, debug=False)
