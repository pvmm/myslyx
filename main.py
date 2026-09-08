"""Compatibility entrypoint for running Myslyx from a source checkout.

`python main.py` behaves exactly like the installed `myslyx` command or
`python -m myslyx`. It is kept for the Hugging Face Space entrypoint and so
the editor can be run straight from the repository without installing the
package (the repo root is on sys.path when this script runs, which makes the
`myslyx` package importable).
"""

from myslyx.app import run

if __name__ == '__main__':
    run()