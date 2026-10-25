import pytest

from auguste.agent.policy import MODULE_TOOLS, OVERRIDES, TOOL_MODULE, Policy, Tier


def test_inventory_has_216_tools_and_overrides_are_known():
    assert len(TOOL_MODULE) == 216
    assert set(OVERRIDES) <= set(TOOL_MODULE)


@pytest.mark.parametrize(
    "name, tier",
    [
        ("get_scene_info", Tier.SAFE),
        ("get_points", Tier.SAFE),
        ("create_node", Tier.MUTATING),
        ("set_parameter", Tier.MUTATING),
        ("import_file", Tier.MUTATING),
        ("execute_python", Tier.DANGEROUS),
        ("execute_hscript", Tier.DANGEROUS),
        ("delete_node", Tier.DANGEROUS),
        ("save_scene", Tier.DANGEROUS),
        ("load_scene", Tier.DANGEROUS),
        ("export_file", Tier.DANGEROUS),
        ("write_cache", Tier.DANGEROUS),
        ("install_hda", Tier.DANGEROUS),
        ("start_render", Tier.DANGEROUS),
        ("stop_houdini", Tier.DANGEROUS),
        ("brand_new_upstream_tool", Tier.DANGEROUS),
    ],
)
def test_tiers(name, tier):
    assert Policy().tier(name) is tier


@pytest.mark.parametrize(
    "name, args",
    [
        ("capture_screenshot", {"output_path": "/tmp/x.png"}),
        ("create_node", {"parent_path": "/obj/geo1", "node_type": "python"}),
        ("build_network", {"parent_path": "/obj", "nodes": [{"type": "python", "name": "p"}]}),
        ("build_network", {"parent_path": "/obj", "nodes": [{"type": "null", "parms": {"python": "x"}}]}),
        ("set_expression", {"node_path": "/obj/a", "parm_name": "tx", "expression": "1", "language": "python"}),
        ("set_parameter", {"node_path": "/obj/a/py", "parm_name": "python", "value": "import os"}),
        ("set_parameters", {"node_path": "/obj/a/py", "params": {"python": "import os"}}),
    ],
)
def test_arguments_escalate_to_dangerous(name, args):
    assert Policy().tier(name, args) is Tier.DANGEROUS


def test_capture_without_output_path_is_safe():
    assert Policy().tier("capture_screenshot", {}) is Tier.SAFE


def test_confirmation_rules():
    default, strict = Policy(), Policy(ask_mutating=True)
    assert default.needs_confirmation("execute_python")
    assert not default.needs_confirmation("create_node")
    assert strict.needs_confirmation("create_node")
    assert not strict.needs_confirmation("get_scene_info")


def test_extra_tiers_for_other_servers():
    policy = Policy(extra_tiers={"rag_search": Tier.SAFE})
    assert policy.tier("rag_search") is Tier.SAFE
