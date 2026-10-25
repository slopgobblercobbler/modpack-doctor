"""Tests for mod dependency graph."""

from modpack_doctor.graph import ModDependencyGraph
from modpack_doctor.models import Dependency, DepType, Environment, LoaderType, ModInfo


def make_mod(mod_id: str, deps=None, provides=None, version="1.0.0") -> ModInfo:
    return ModInfo(
        id=mod_id,
        name=mod_id.capitalize(),
        version=version,
        loader=LoaderType.FABRIC,
        file_path=f"{mod_id}.jar",
        file_name=f"{mod_id}.jar",
        dependencies=deps or [],
        provides=provides or [],
    )


def test_graph_construction_and_provides():
    mod_a = make_mod("mod_a", deps=[Dependency(mod_id="alias_b")])
    mod_b = make_mod("mod_b", provides=["alias_b"])

    graph = ModDependencyGraph.from_mods([mod_a, mod_b])
    assert graph.resolve_mod_id("mod_a") == "mod_a"
    assert graph.resolve_mod_id("alias_b") == "mod_b"
    assert graph.resolve_mod_id("unknown") is None
    assert graph.get_mod("alias_b") == mod_b


def test_detect_cycles():
    # Mod A -> Mod B, and Mod B has TWO edges back to Mod A to trigger line 80->66
    mod_a = make_mod("mod_a", deps=[Dependency(mod_id="mod_b")])
    mod_b = make_mod("mod_b", deps=[Dependency(mod_id="mod_a"), Dependency(mod_id="mod_a")])

    graph = ModDependencyGraph.from_mods([mod_a, mod_b])
    cycles = graph.detect_cycles()
    assert len(cycles) > 0
    cycle_nodes = set(cycles[0])
    assert "mod_a" in cycle_nodes and "mod_b" in cycle_nodes


def test_detect_cycles_none():
    mod_a = make_mod("mod_a", deps=[Dependency(mod_id="mod_b")])
    mod_b = make_mod("mod_b", deps=[Dependency(mod_id="mod_c")])
    mod_c = make_mod("mod_c")

    graph = ModDependencyGraph.from_mods([mod_a, mod_b, mod_c])
    cycles = graph.detect_cycles()
    assert len(cycles) == 0


def test_to_ascii_tree():
    mod_a = make_mod("mod_a", deps=[Dependency(mod_id="mod_b"), Dependency(mod_id="missing_mod")])
    mod_b = make_mod("mod_b")

    graph = ModDependencyGraph.from_mods([mod_a, mod_b])
    tree_all = graph.to_ascii_tree()
    assert "mod_a@1.0.0" in tree_all
    assert "mod_b@1.0.0" in tree_all
    assert "missing_mod (*) [MISSING]" in tree_all

    tree_single = graph.to_ascii_tree(root_id="mod_a")
    assert "mod_a@1.0.0" in tree_single


def test_detect_cycles_diamond_and_missing():
    # Mod A -> Mod B, Mod A -> Mod C, Mod B -> Mod D, Mod C -> Mod D (Diamond, no cycle)
    # Also Mod D -> Mod Missing (missing node)
    mod_a = make_mod("mod_a", deps=[Dependency(mod_id="mod_b"), Dependency(mod_id="mod_c")])
    mod_b = make_mod("mod_b", deps=[Dependency(mod_id="mod_d")])
    mod_c = make_mod("mod_c", deps=[Dependency(mod_id="mod_d")])
    mod_d = make_mod("mod_d", deps=[Dependency(mod_id="missing_dep")])

    graph = ModDependencyGraph.from_mods([mod_a, mod_b, mod_c, mod_d])
    cycles = graph.detect_cycles()
    assert len(cycles) == 0


def test_to_ascii_tree_circular_and_depth_limit():
    mod_a = make_mod("mod_a", deps=[Dependency(mod_id="mod_b")])
    mod_b = make_mod("mod_b", deps=[Dependency(mod_id="mod_a")])

    graph = ModDependencyGraph.from_mods([mod_a, mod_b])
    tree_circ = graph.to_ascii_tree(root_id="mod_a", max_depth=10)
    assert "[circular reference]" in tree_circ

    tree_depth = graph.to_ascii_tree(root_id="mod_a", max_depth=1)
    assert "... (depth limit reached)" in tree_depth


def test_to_mermaid_and_dot():
    mod_a = make_mod(
        "mod_a",
        deps=[
            Dependency(mod_id="mod_b", version_range=">=1.0", dep_type=DepType.REQUIRED),
            Dependency(mod_id="mod_c", version_range="*", dep_type=DepType.OPTIONAL),
        ],
    )
    mod_b = make_mod("mod_b")
    mod_c = make_mod("mod_c")

    graph = ModDependencyGraph.from_mods([mod_a, mod_b, mod_c])

    mermaid = graph.to_mermaid()
    assert "graph TD" in mermaid
    assert "mod_a" in mermaid
    assert "-->" in mermaid
    assert "-.->" in mermaid

    dot = graph.to_dot()
    assert "digraph ModpackDependencies" in dot
    assert '"mod_a"' in dot
    assert "solid" in dot
    assert "dashed" in dot
