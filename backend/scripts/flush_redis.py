import os
import sys

# Ensure backend directory is in path so we can import workers.tasks
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from workers.tasks import celery_app

def flush():
    print("Flushing Celery queue...")
    celery_app.control.purge()
    print("Done. Old tasks have been purged.")

if __name__ == "__main__":
    flush()
