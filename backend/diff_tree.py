import utils


class DiffTree(object):

    def __init__(self, differ):
        self.nodes = {}
        self.children_map = {}

        # Parents of leaf nodes only
        self.leaf_parents = {}

        # Create the nested array structure that will be the tree.
        self.tree = []
        self.root = None

        self.node_parent_ids = {}

        self.differ = differ

        self.create_file_tree()

    def merge(self, other):
        """Combine this diff tree with another (only so it can be cached/uncached)"""
        self.nodes.update(other.nodes)
        self.children_map.update(other.children_map)
        self.tree.extend(other.tree)
        return self

    def get_tree(self):
        return self.tree

    def get_children_map(self):
        return self.children_map

    def get_children(self, parent_node):
        key = parent_node["key"]
        if key not in self.children_map:
            self.children_map[key] = []
        return self.children_map[key]

    def add_child(self, parent_node, child):
        key = parent_node["key"]
        if key not in self.children_map:
            self.children_map[key] = []
        self.children_map[key].append(child)

    def create_node(self, path: str, is_dir=True, is_leaf=False):
        """Create a node, allowing for children to be added later."""

        if path in self.nodes:
            return

        if self.differ.diff_type == "disk":
            p = utils.ensure_posix(path)
            parent_id = None if p.parent == p else str(p.parent)

            if parent_id is None:
                text = "/"
            else:
                text = p.name
            key = str(p)
        elif self.differ.diff_type == "process":
            node_id = path
            text = node_id
            pid = node_id.split("-")[-1]
            key = pid

        # Defaults (for created parent nodes, mostly)
        status = "unchanged"
        lines_added = 0
        lines_removed = 0

        diff = self.differ.diff(path)

        if diff is not None:
            status = diff.status
            lines_added = diff.lines_added
            lines_removed = diff.lines_removed

            if diff.title:
                text = diff.title

            # This gets fixed later.
            is_leaf = not diff.is_dir
            is_dir = diff.is_dir

            ppid = diff.ppid
            if ppid is not None:
                # Save which node is this node's parent, if any.
                self.node_parent_ids[pid] = ppid

        node = {
            "title": text,
            "key": key,
            "isLeaf": is_leaf,
            "isDirectory": is_dir,
            "children": [],
            "status": status,
            "linesAdded": lines_added,
            "linesRemoved": lines_removed,
            "numChildren": 0,
            "numDirectChildren": 0,
        }
        self.nodes[key] = node
        return node

    def create_root_process_node(self):
        key = "Processes"
        node = {
            "title": key,
            "key": key,
            "isLeaf": False,
            "isDirectory": False,
            "children": [],
            "status": "modified",
            "linesAdded": 0,
            "linesRemoved": 0,
            "numChildren": 0,
            "numDirectChildren": 0,
        }
        self.nodes[key] = node
        self.node_parent_ids[key] = key
        self.root = node
        return node

    def get_parent(self, node):
        if self.differ.diff_type == "disk":
            p = utils.ensure_posix(node["key"])
            parent_path = str(p.parent)
            parent_node = self.nodes.get(parent_path)
            return parent_node

        elif self.differ.diff_type == "process":
            parent_id = self.node_parent_ids.get(node["key"])
            parent = self.nodes.get(parent_id)
            if parent is None:
                return self.root
            return parent

    def create_file_tree(self):

        # If we're calling this function a second time, we don't need to do anything, the tree is already generated.
        if len(self.tree) > 0:
            return

        def create_parent_nodes(path: str):

            p = utils.ensure_posix(path)
            parent_paths = p.parents
            for parent_path in parent_paths:
                parent_path = str(parent_path)
                if parent_path not in self.nodes:
                    self.nodes[parent_path] = self.create_node(
                        parent_path, is_dir=True)

        paths = self.differ.diffs.keys()

        # Create flat node index.
        for path in paths:
            if self.differ.diff_type == "disk":
                create_parent_nodes(path)

            self.create_node(path)

        if self.differ.diff_type == "process" and len(self.differ.diffs) > 0:
            self.create_root_process_node()

        # Link up the nodes to their parents
        for path, node in sorted(self.nodes.items()):

            parent_node = self.get_parent(node)

            # If this node is the root, just add it.
            if parent_node == node:
                self.root = node
                self.tree.append(node)
                continue

            # Otherwise, insert this node underneath the parent node.
            # Sorting paths guarantees that parents are inserted first, then children.
            if parent_node:
                # Link this node to its parent
                self.add_child(parent_node, node)

        if len(self.tree) > 0:
            root = self.tree[0]
        else:
            root = []

        if len(self.tree) == 0:
            return []
        # Fix the tree
        for node in reversed(list(self.traverse(root))):
            # Directories without children should be leaves.
            children = self.get_children(node)
            if len(children) == 0:
                node["isLeaf"] = True
            else:
                node["isLeaf"] = False
                # Count the number of file descendants of each node.
                for child in children:
                    num_child_children = 0
                    # Don't count directories as children.
                    if not child["isDirectory"]:
                        num_child_children += 1
                        node["numDirectChildren"] += 1

                    num_child_children += child["numChildren"]

                    node["numChildren"] += num_child_children

        return

    def traverse(self, node):
        yield node
        for child in self.get_children(node):
            yield from self.traverse(child)
