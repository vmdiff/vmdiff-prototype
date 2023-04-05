import inspect
import os
import sys
import time

import logging

from flask import Flask, jsonify, request, render_template, send_from_directory

import config

# Python Crimes to import from a local module
currentdir = os.path.dirname(os.path.abspath(
    inspect.getfile(inspect.currentframe())))
backend_dir = os.path.join(currentdir, "backend")
sys.path.insert(0, backend_dir)


if config.dev:
    from backend import vmdiff
    vmdiff.Main()

try:
    import diffcache  # noqa
except ImportError:
    from backend import diffcache


REACT_BUILD_DIR = config.REACT_BUILD_DIR

app = Flask(
    __name__, static_folder=f"{REACT_BUILD_DIR}/static", template_folder=f"{REACT_BUILD_DIR}")

logging.info(f"Waiting for results at {config.RUN_TREE_PATH}....")

if not os.path.exists(config.RUN_TREE_PATH):
    logging.critical(
        f"No results found at {config.RUN_TREE_PATH}. Generate results first?")
    sys.exit(1)

cache = diffcache.DiffCache(
    config.RUN_DISK_PATH, config.RUN_TREE_PATH, config.RUN_MEMORY_PATH)
while True:
    try:
        tree, children_map = cache.get_tree_data_from_cache()
        break
    except FileNotFoundError:
        time.sleep(3)


logging.debug(f"Tree: {len(tree)}, children: {len(children_map)}")


@app.route("/children")
def get_children_handler():
    key = request.args.get("key")

    node_children = children_map[key]
    response = jsonify(node_children)
    response.headers.add('Access-Control-Allow-Origin', '*')

    return response


@app.route("/diff")
def get_diff():

    key = request.args.get("key")

    diff = cache.get_diff(key)
    if diff is None:
        logging.warning(f"No diff found for {key}")
        result = None
    else:
        result = diff.diff_lines

    response = jsonify(result)
    response.headers.add('Access-Control-Allow-Origin', '*')

    # to start with, just return the directories, and let the user expand out the files.
    return response


@app.route("/changed_files")
def get_changed_files():
    response = jsonify(tree)
    response.headers.add('Access-Control-Allow-Origin', '*')

    # To start with, just return the directories, and let the user expand out the files.
    return response


@app.route("/json/<path:path>")
def json(path):
    json_dir = f"{cache.tree_path}/json"
    return send_from_directory(json_dir, path)


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":

    app.run("0.0.0.0", debug=True)
