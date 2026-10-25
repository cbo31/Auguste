"""Tool tiers for fxhoudinimcp tools. Source of truth: docs/fxhoudinimcp-tools.md.

Lookup order: argument escalation, name override, module default. Unknown
tools are dangerous.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Tier(str, Enum):
    SAFE = "safe"
    MUTATING = "mutating"
    DANGEROUS = "dangerous"


MODULE_TOOLS: dict[str, str] = {
    "animation": "set_keyframe set_keyframes delete_keyframe get_keyframes set_frame get_frame set_frame_range set_playback_range playbar_control",
    "cache": "list_caches get_cache_status clear_cache write_cache",
    "chops": "get_chop_data create_chop_node list_chop_channels export_chop_to_parm",
    "code": "execute_python reload_plugin execute_hscript evaluate_expression get_env_variable get_file_references set_update_mode",
    "context": "get_network_overview get_cook_chain explain_node get_selection set_selection get_scene_summary compare_snapshots get_node_errors_detailed",
    "cops": "get_cop_info get_cop_geometry get_cop_layer create_cop_node set_cop_flags list_cop_node_types get_cop_vdb",
    "dops": "get_simulation_info list_dop_objects get_dop_object get_dop_field get_dop_relationships step_simulation reset_simulation get_sim_memory_usage",
    "geometry": "get_geometry_info get_points get_prims get_attrib_values set_detail_attrib get_groups get_group_members get_bounding_box get_attribute_info sample_geometry get_prim_intrinsics find_nearest_point get_attrib_stats get_volume_info sample_volume compare_volumes",
    "graph": "build_network verify_network get_node_card find_expensive_nodes cook_frame_range get_cook_status",
    "hda": "list_installed_hdas get_hda_info install_hda uninstall_hda reload_hda create_hda update_hda get_hda_sections get_hda_section_content set_hda_section_content list_hda_versions set_hda_interface edit_hda_interface",
    "help": "search_help get_help_page get_workflow_guide",
    "lops": "get_stage_info get_usd_prim list_usd_prims get_usd_attribute get_usd_attributes get_usd_world_transform get_usd_layers get_usd_prim_stats get_last_modified_prims create_lop_node set_usd_attribute get_usd_bound_material get_usd_materials find_usd_prims get_usd_composition get_usd_variants inspect_usd_layer create_light list_lights set_light_properties create_light_rig",
    "materials": "list_materials get_material_info create_material_network list_material_types",
    "nodes": "create_node delete_node rename_node copy_node move_node get_node_info list_children find_nodes list_node_types change_node_type press_button connect_nodes connect_nodes_batch disconnect_node reorder_inputs set_node_flags layout_children set_node_position set_node_color create_network_box create_sticky_note set_object_transform",
    "parameters": "get_parameter set_parameter set_parameters get_parameter_schema get_parm_references get_parm_template_tree set_expression get_expression revert_parameter link_parameters lock_parameter create_spare_parameter create_spare_parameters promote_vop_parameters get_parameters",
    "rendering": "render_viewport render_quad_view list_render_nodes get_render_settings set_render_settings create_render_node start_render render_node_network get_render_progress render_sheet",
    "scene": "get_houdini_connection_status get_scene_info new_scene save_scene load_scene import_file export_file get_context_info undo redo",
    "session": "connect_houdini start_houdini stop_houdini",
    "shelf": "list_shelf_tools get_shelf_tool_script run_shelf_tool",
    "takes": "list_takes get_current_take set_current_take create_take",
    "tops": "get_top_network_info cook_top_node cancel_top_cook pause_top_cook dirty_work_items get_work_item_states get_work_item_info get_pdg_graph generate_static_items get_top_scheduler_info get_failed_work_items get_top_logs",
    "vex": "create_wrangle set_wrangle_code get_wrangle_code create_vex_expression validate_vex",
    "viewport": "list_panes get_viewport_info set_viewport_camera set_viewport_display set_viewport_renderer frame_selection frame_all set_viewport_direction capture_screenshot capture_network_editor set_current_network find_error_nodes log_status set_viewer_context",
    "workflows": "setup_pyro_sim setup_rbd_sim setup_flip_sim setup_vellum_sim create_material assign_material build_sop_chain setup_render",
}

MODULE_DEFAULTS: dict[str, Tier] = {
    "animation": Tier.MUTATING, "cache": Tier.SAFE, "chops": Tier.MUTATING,
    "code": Tier.DANGEROUS, "context": Tier.SAFE, "cops": Tier.MUTATING,
    "dops": Tier.SAFE, "geometry": Tier.SAFE, "graph": Tier.MUTATING,
    "hda": Tier.DANGEROUS, "help": Tier.SAFE, "lops": Tier.SAFE,
    "materials": Tier.MUTATING, "nodes": Tier.MUTATING, "parameters": Tier.MUTATING,
    "rendering": Tier.DANGEROUS, "scene": Tier.DANGEROUS, "session": Tier.DANGEROUS,
    "shelf": Tier.SAFE, "takes": Tier.MUTATING, "tops": Tier.MUTATING,
    "vex": Tier.MUTATING, "viewport": Tier.MUTATING, "workflows": Tier.MUTATING,
}


def _tiers(tier: Tier, names: str) -> dict[str, Tier]:
    return {name: tier for name in names.split()}


OVERRIDES: dict[str, Tier] = {
    **_tiers(Tier.SAFE, """
        get_keyframes get_frame get_chop_data list_chop_channels
        get_env_variable get_file_references
        get_cop_info get_cop_geometry get_cop_layer list_cop_node_types get_cop_vdb
        verify_network get_node_card find_expensive_nodes get_cook_status
        list_installed_hdas get_hda_info get_hda_sections get_hda_section_content list_hda_versions
        list_materials get_material_info list_material_types
        get_node_info list_children find_nodes list_node_types
        get_parameter get_parameters get_parameter_schema get_parm_references get_parm_template_tree get_expression
        list_render_nodes get_render_settings get_render_progress
        get_houdini_connection_status get_scene_info get_context_info
        list_takes get_current_take
        get_top_network_info get_work_item_states get_work_item_info get_pdg_graph
        get_top_scheduler_info get_failed_work_items get_top_logs
        get_wrangle_code validate_vex
        list_panes get_viewport_info find_error_nodes capture_network_editor capture_screenshot
    """),
    **_tiers(Tier.MUTATING, """
        set_selection set_detail_attrib
        create_lop_node set_usd_attribute create_light set_light_properties create_light_rig
        set_render_settings create_render_node import_file undo redo connect_houdini
    """),
    **_tiers(Tier.DANGEROUS, """
        clear_cache write_cache step_simulation reset_simulation cook_frame_range
        delete_node change_node_type press_button run_shelf_tool cook_top_node
    """),
}

TOOL_MODULE: dict[str, str] = {
    name: module for module, names in MODULE_TOOLS.items() for name in names.split()
}

# Tools that write a file when output_path is given.
_FILE_WRITERS = {"capture_screenshot", "capture_network_editor", "render_viewport", "render_quad_view", "render_sheet"}
# Tools whose node type argument can create a Python node that runs code on cook.
_NODE_CREATORS = {"create_node", "change_node_type", "build_network", "create_lop_node", "create_cop_node", "create_chop_node"}
_CODE_PARMS = {"python", "pythoncode", "code", "script"}


def _escalates(name: str, args: Mapping[str, Any]) -> bool:
    """Argument-based escalation for the gaps listed in the tool inventory."""
    if name in _FILE_WRITERS and args.get("output_path"):
        return True
    if name in _NODE_CREATORS:
        types = [args.get("node_type"), args.get("new_type")]
        types += [n.get("type") or n.get("node_type") for n in args.get("nodes") or [] if isinstance(n, Mapping)]
        if any(isinstance(t, str) and "python" in t.lower() for t in types):
            return True
    if name in {"set_expression", "create_vex_expression"} and str(args.get("language", "")).lower() == "python":
        return True
    if name in {"set_parameter", "set_parameters", "build_network"}:
        parms = [args.get("parm_name"), *(args.get("params") or {})]
        for node in args.get("nodes") or []:
            if isinstance(node, Mapping) and isinstance(node.get("parms"), Mapping):
                parms += list(node["parms"])
        if any(isinstance(p, str) and p.lower() in _CODE_PARMS for p in parms):
            return True
    return False


@dataclass
class Policy:
    """Decides the tier of a tool call and whether the user must approve it.

    Dangerous tools always ask. Mutating tools ask only when ask_mutating is set.
    extra_tiers lets other MCP servers (auguste-mcp) register their own tools.
    """

    ask_mutating: bool = False
    extra_tiers: dict[str, Tier] = field(default_factory=dict)

    def tier(self, name: str, args: Mapping[str, Any] | None = None) -> Tier:
        args = args or {}
        if name in self.extra_tiers:
            base = self.extra_tiers[name]
        elif name in OVERRIDES:
            base = OVERRIDES[name]
        elif name in TOOL_MODULE:
            base = MODULE_DEFAULTS[TOOL_MODULE[name]]
        else:
            return Tier.DANGEROUS
        if _escalates(name, args):
            return Tier.DANGEROUS
        return base

    def needs_confirmation(self, name: str, args: Mapping[str, Any] | None = None) -> bool:
        tier = self.tier(name, args)
        return tier is Tier.DANGEROUS or (tier is Tier.MUTATING and self.ask_mutating)
