# -*- coding: utf-8 -*-

"""Functions common to test suites.
"""

"""License:
    Copyright 2020 The Cytoscape Consortium

    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
    documentation files (the "Software"), to deal in the Software without restriction, including without limitation
    the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
    and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all copies or substantial portions
    of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
    WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
    OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
    OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

import functools


def __init__(self):
    pass

# Decorators inspired by https://realpython.com/primer-on-python-decorators/
def print_entry_exit(func):
    """Print the function signature and return value"""

    @functools.wraps(func)
    def wrapper_entry_exit(*args, **kwargs):
        print(f"Into {func.__name__}()")
        try:
            value = func(*args, **kwargs)
            print(f"Out of {func.__name__!r}")
            return value
        except Exception as e:
            print(f"{func.__name__!r} exception {e!r}")
            raise

    return wrapper_entry_exit
