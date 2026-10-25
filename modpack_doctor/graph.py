"""Dependency graph construction, cycle detection, and graph visualization."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from modpack_doctor.models import Dependency, DepType, ModInfo


class ModDependencyGraph:
    """Directed dependency graph of Minecraft mods."""

    def __init__(self) -> None:
        self.nodes: Dict[str, ModInfo] = {}
        # mod_id -> list of dependencies
        self.edges: Dict[str, List[Dependency]] = defaultdict(list)
        # mod_id -> list of (dependent_id, dependency)
        self.reverse_edges: Dict[str, List[Tuple[str, Dependency]]] = defaultdict(list)
        # provides alias -> real mod_id
        self.provides_map: Dict[str, str] = {}

    @classmethod
    def from_mods(cls, mods: List[ModInfo]) -> ModDependencyGraph:
        """Construct graph from a list of mods."""
        graph = cls()
        for mod in mods:
            graph.add_mod(mod)
        return graph

    def add_mod(self, mod: ModInfo) -> None:
        """Add mod node to graph."""
        self.nodes[mod.id] = mod
        for alias in mod.provides:
            self.provides_map[alias] = mod.id

        for dep in mod.dependencies:
            self.edges[mod.id].append(dep)
            self.reverse_edges[dep.mod_id].append((mod.id, dep))

    def resolve_mod_id(self, target_id: str) -> Optional[str]:
        """Resolve mod ID considering 'provides' aliases."""
        if target_id in self.nodes:
            return target_id
        if target_id in self.provides_map:
            return self.provides_map[target_id]
        return None

    def get_mod(self, target_id: str) -> Optional[ModInfo]:
        """Retrieve ModInfo by id or provided alias."""
        resolved = self.resolve_mod_id(target_id)
        if resolved:
            return self.nodes.get(resolved)
        return None

    def detect_cycles(self) -> List[List[str]]:
        """Detect circular dependencies using DFS cycle detection."""
        cycles: List[List[str]] = []
        visited: Set[str] = set()
        rec_stack: List[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.append(node)

            for dep in self.edges.get(node, []):
                # Only check required dependencies for cycles
                if dep.dep_type != DepType.REQUIRED:
                    continue

                target_id = self.resolve_mod_id(dep.mod_id)
                if not target_id or target_id not in self.nodes:
                    continue

                if target_id not in visited:
                    dfs(target_id)
                elif target_id in rec_stack:
                    cycle_start = rec_stack.index(target_id)
                    cycle_path = rec_stack[cycle_start:] + [target_id]
                    if cycle_path not in cycles:
                        cycles.append(cycle_path)

            rec_stack.pop()

        for mod_id in list(self.nodes.keys()):
            if mod_id not in visited:
                dfs(mod_id)

        return cycles

    def to_ascii_tree(self, root_id: Optional[str] = None, max_depth: int = 8) -> str:
        """Render dependency graph as ASCII tree."""
        lines: List[str] = []

        roots = [root_id] if root_id and root_id in self.nodes else sorted(self.nodes.keys())

        visited_in_path: Set[str] = set()

        def render_node(mod_id: str, prefix: str, is_last: bool, depth: int) -> None:
            if depth > max_depth:
                lines.append(f"{prefix}{'└── ' if is_last else '├── '}... (depth limit reached)")
                return

            mod = self.nodes.get(mod_id)
            node_label = f"{mod_id}@{mod.version}" if mod else mod_id
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{node_label}")

            if mod_id in visited_in_path:
                lines.append(f"{prefix}{'    ' if is_last else '│   '}└── [circular reference]")
                return

            visited_in_path.add(mod_id)
            child_prefix = prefix + ("    " if is_last else "│   ")

            deps = [d for d in self.edges.get(mod_id, []) if d.dep_type == DepType.REQUIRED]
            for idx, dep in enumerate(deps):
                dep_last = (idx == len(deps) - 1)
                resolved = self.resolve_mod_id(dep.mod_id)
                if resolved:
                    render_node(resolved, child_prefix, dep_last, depth + 1)
                else:
                    target_label = f"{dep.mod_id} ({dep.version_range}) [MISSING]"
                    lines.append(f"{child_prefix}{'└── ' if dep_last else '├── '}{target_label}")

            visited_in_path.remove(mod_id)

        for i, root in enumerate(roots):
            if root_id is None:
                # If printing all roots, only show roots that have dependencies or are top-level
                is_dependent = bool(self.reverse_edges.get(root))
                # Only print top-level roots if rendering full forest
                if is_dependent and len(roots) > 1:
                    continue
            render_node(root, "", is_last=True, depth=1)

        return "\n".join(lines)

    def to_mermaid(self) -> str:
        """Export dependency graph in Mermaid diagram syntax."""
        lines = ["graph TD"]
        for mod_id, mod in sorted(self.nodes.items()):
            label = f"{mod_id} [{mod.version}]".replace('"', "'")
            lines.append(f'    {mod_id}["{label}"]')

        for mod_id, deps in sorted(self.edges.items()):
            for dep in deps:
                target_id = self.resolve_mod_id(dep.mod_id) or dep.mod_id
                style = "-->" if dep.dep_type == DepType.REQUIRED else "-.->"
                lines.append(f'    {mod_id} {style}|"{dep.version_range}"| {target_id}')

        return "\n".join(lines)

    def to_dot(self) -> str:
        """Export dependency graph in Graphviz DOT syntax."""
        lines = ["digraph ModpackDependencies {", "    rankdir=LR;", "    node [shape=box, fontname=sans-serif];"]
        for mod_id, mod in sorted(self.nodes.items()):
            lines.append(f'    "{mod_id}" [label="{mod_id}\\n{mod.version}"];')

        for mod_id, deps in sorted(self.edges.items()):
            for dep in deps:
                target_id = self.resolve_mod_id(dep.mod_id) or dep.mod_id
                style = "solid" if dep.dep_type == DepType.REQUIRED else "dashed"
                color = "black" if dep.dep_type == DepType.REQUIRED else "gray"
                lines.append(f'    "{mod_id}" -> "{target_id}" [label="{dep.version_range}", style={style}, color={color}];')

        lines.append("}")
        return "\n".join(lines)
