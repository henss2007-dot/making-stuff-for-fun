import os
import sys
import tempfile

# Keep tests away from the real ~/.wordmine
os.environ.setdefault("WORDMINE_HOME", tempfile.mkdtemp(prefix="wordmine-test-"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
