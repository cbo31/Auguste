# fxhoudinimcp tool inventory and tiers

Source: `fxhoudinimcp==2.28.2` (pinned in `pyproject.toml`), 216 tools across 22 modules, extracted from `fxhoudinimcp/tools/*.py`. This table feeds `src/auguste/agent/policy.py`.

## Tiers

- **safe**: read-only. Runs without asking.
- **mutating**: changes the live scene but is undoable (Houdini undo) or trivially reversible. Configurable: auto-run or ask.
- **dangerous**: always asks in the panel. Runs arbitrary code, deletes, writes or overwrites files on disk, replaces the scene, installs/changes HDAs, starts long cooks/renders, or controls the Houdini process.

Rule for `policy.py`: look up the tool **name** first (overrides below), then fall back to the **module default**. Unknown tools (e.g. new upstream versions) default to **dangerous**.

## Module defaults and overrides

| Module | Default | safe overrides | dangerous overrides |
|---|---|---|---|
| animation | mutating | `get_keyframes`, `get_frame` | — |
| cache | safe | — | `clear_cache`, `write_cache` |
| chops | mutating | `get_chop_data`, `list_chop_channels` | — |
| code | dangerous | `get_env_variable`, `get_file_references` | (`execute_python`, `execute_hscript`, `reload_plugin`, `evaluate_expression`, `set_update_mode` stay dangerous) |
| context | safe | — | — (`set_selection` → mutating) |
| cops | mutating | `get_cop_info`, `get_cop_geometry`, `get_cop_layer`, `list_cop_node_types`, `get_cop_vdb` | — |
| dops | safe | — | `step_simulation`, `reset_simulation` (mutating would be acceptable; long-running) |
| geometry | safe | — | — (`set_detail_attrib` → mutating) |
| graph | mutating | `verify_network`, `get_node_card`, `find_expensive_nodes`, `get_cook_status` | `cook_frame_range` |
| hda | dangerous | `list_installed_hdas`, `get_hda_info`, `get_hda_sections`, `get_hda_section_content`, `list_hda_versions` | — |
| help | safe | — | — |
| lops | safe | — | — (`create_lop_node`, `set_usd_attribute`, `create_light`, `set_light_properties`, `create_light_rig` → mutating) |
| materials | mutating | `list_materials`, `get_material_info`, `list_material_types` | — |
| nodes | mutating | `get_node_info`, `list_children`, `find_nodes`, `list_node_types` | `delete_node`, `change_node_type`, `press_button` |
| parameters | mutating | `get_parameter`, `get_parameters`, `get_parameter_schema`, `get_parm_references`, `get_parm_template_tree`, `get_expression` | — |
| rendering | dangerous | `list_render_nodes`, `get_render_settings`, `get_render_progress` | — (`set_render_settings`, `create_render_node` → mutating) |
| scene | dangerous | `get_houdini_connection_status`, `get_scene_info`, `get_context_info` | (`new_scene`, `save_scene`, `load_scene`, `export_file` stay dangerous; `import_file`, `undo`, `redo` → mutating) |
| session | dangerous | — | `start_houdini`, `stop_houdini` (`connect_houdini` → mutating) |
| shelf | safe | — | `run_shelf_tool` |
| takes | mutating | `list_takes`, `get_current_take` | — |
| tops | mutating | `get_top_network_info`, `get_work_item_states`, `get_work_item_info`, `get_pdg_graph`, `get_top_scheduler_info`, `get_failed_work_items`, `get_top_logs` | `cook_top_node` |
| vex | mutating | `get_wrangle_code`, `validate_vex` | — |
| viewport | mutating | `list_panes`, `get_viewport_info`, `find_error_nodes`, `capture_network_editor`*, `capture_screenshot`* | — |
| workflows | mutating | — | — |

\* Capture/render tools that take `output_path` (`capture_screenshot`, `capture_network_editor`, `render_viewport`, `render_quad_view`, `render_sheet`) write files. Treat them as **dangerous when `output_path` is set**, otherwise safe (viewport captures) or as listed.

## Known gaps the policy can't catch by name

- `create_node`/`create_wrangle` can create a Python SOP or set Python code in a parameter, which runs on cook. `set_parameter`/`set_expression` can set a Python expression. The policy should inspect arguments (node type `python`, `language="python"`) and escalate to dangerous.
- `evaluate_expression` with hscript can call `system()`; kept dangerous.

## Full tool list by module

animation: set_keyframe set_keyframes delete_keyframe get_keyframes set_frame get_frame set_frame_range set_playback_range playbar_control
cache: list_caches get_cache_status clear_cache write_cache
chops: get_chop_data create_chop_node list_chop_channels export_chop_to_parm
code: execute_python reload_plugin execute_hscript evaluate_expression get_env_variable get_file_references set_update_mode
context: get_network_overview get_cook_chain explain_node get_selection set_selection get_scene_summary compare_snapshots get_node_errors_detailed
cops: get_cop_info get_cop_geometry get_cop_layer create_cop_node set_cop_flags list_cop_node_types get_cop_vdb
dops: get_simulation_info list_dop_objects get_dop_object get_dop_field get_dop_relationships step_simulation reset_simulation get_sim_memory_usage
geometry: get_geometry_info get_points get_prims get_attrib_values set_detail_attrib get_groups get_group_members get_bounding_box get_attribute_info sample_geometry get_prim_intrinsics find_nearest_point get_attrib_stats get_volume_info sample_volume compare_volumes
graph: build_network verify_network get_node_card find_expensive_nodes cook_frame_range get_cook_status
hda: list_installed_hdas get_hda_info install_hda uninstall_hda reload_hda create_hda update_hda get_hda_sections get_hda_section_content set_hda_section_content list_hda_versions set_hda_interface edit_hda_interface
help: search_help get_help_page get_workflow_guide
lops: get_stage_info get_usd_prim list_usd_prims get_usd_attribute get_usd_attributes get_usd_world_transform get_usd_layers get_usd_prim_stats get_last_modified_prims create_lop_node set_usd_attribute get_usd_bound_material get_usd_materials find_usd_prims get_usd_composition get_usd_variants inspect_usd_layer create_light list_lights set_light_properties create_light_rig
materials: list_materials get_material_info create_material_network list_material_types
nodes: create_node delete_node rename_node copy_node move_node get_node_info list_children find_nodes list_node_types change_node_type press_button connect_nodes connect_nodes_batch disconnect_node reorder_inputs set_node_flags layout_children set_node_position set_node_color create_network_box create_sticky_note set_object_transform
parameters: get_parameter set_parameter set_parameters get_parameter_schema get_parm_references get_parm_template_tree set_expression get_expression revert_parameter link_parameters lock_parameter create_spare_parameter create_spare_parameters promote_vop_parameters get_parameters
rendering: render_viewport render_quad_view list_render_nodes get_render_settings set_render_settings create_render_node start_render render_node_network get_render_progress render_sheet
scene: get_houdini_connection_status get_scene_info new_scene save_scene load_scene import_file export_file get_context_info undo redo
session: connect_houdini start_houdini stop_houdini
shelf: list_shelf_tools get_shelf_tool_script run_shelf_tool
takes: list_takes get_current_take set_current_take create_take
tops: get_top_network_info cook_top_node cancel_top_cook pause_top_cook dirty_work_items get_work_item_states get_work_item_info get_pdg_graph generate_static_items get_top_scheduler_info get_failed_work_items get_top_logs
vex: create_wrangle set_wrangle_code get_wrangle_code create_vex_expression validate_vex
viewport: list_panes get_viewport_info set_viewport_camera set_viewport_display set_viewport_renderer frame_selection frame_all set_viewport_direction capture_screenshot capture_network_editor set_current_network find_error_nodes log_status set_viewer_context
workflows: setup_pyro_sim setup_rbd_sim setup_flip_sim setup_vellum_sim create_material assign_material build_sop_chain setup_render
