import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# session logs from tests go to a scratch folder, never to the player's logs
import tempfile  # noqa: E402

os.environ.setdefault("KINDRED_SESSION_DIR", tempfile.mkdtemp(prefix="kindred-sessions-"))
