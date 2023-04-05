import pathlib 

def ensure_posix(path):
    if path.startswith("\\"):
        # Force POSIX path so that we can create the directory structure in the Docker container, even if the path is Windows.
        path = pathlib.PureWindowsPath(path).as_posix()
    path = pathlib.Path(path)
    return path