import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from app.core.security import hash_password, verify_password

start = time.time()
h = hash_password("Priya@1234")
print(f"Hash time: {time.time() - start:.3f}s")

start = time.time()
v = verify_password("Priya@1234", h)
print(f"Verify time: {time.time() - start:.3f}s")
print(f"Valid: {v}")
