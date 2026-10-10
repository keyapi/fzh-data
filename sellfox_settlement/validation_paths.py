"""Keep private validation data outside every Git checkout and original inputs."""
from pathlib import Path


def private_output(path, *, input_root=None):
    output = Path(path).resolve()
    if any((ancestor / '.git').exists() for ancestor in [output, *output.parents]):
        raise ValueError('private output cannot be inside a Git checkout')
    if input_root is not None:
        source = Path(input_root).resolve()
        if output == source or source in output.parents:
            raise ValueError('private output cannot be inside original input')
    return output
