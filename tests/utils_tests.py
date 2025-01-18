from contextlib import contextmanager
import time


@contextmanager
def timer(name):
    start = time.time()
    yield
    end = time.time()
    print(f"{name} took {end - start:.2f} seconds")
