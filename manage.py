"""CLI: python manage.py migrate | seed | reset | run"""
import os
import sys

import db


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "run"
    if cmd == "reset":
        p = db.default_db_path()
        if os.path.exists(p):
            os.remove(p)
        cmd = "setup"
    if cmd in ("migrate", "setup"):
        with db.connect() as c:
            print("migrations applied:", db.migrate(c) or "none (up to date)")
    if cmd in ("seed", "setup"):
        with db.connect() as c:
            db.migrate(c)
            print("seed files run:", db.seed(c))
    if cmd == "run":
        from app import create_app
        create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))
    elif cmd not in ("migrate", "seed", "setup"):
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
