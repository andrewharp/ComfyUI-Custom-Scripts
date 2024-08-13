import glob
import inspect
import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime

import curie.tools.update_workflow

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pysssss
from aiohttp import web
from server import PromptServer

root_directory = os.path.dirname(inspect.getfile(PromptServer))
workflows_directory = os.path.join(root_directory, "pysssss-workflows")
workflows_directory = pysssss.get_config_value(
    "workflows.directory", workflows_directory)

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}


@PromptServer.instance.routes.get("/pysssss/workflows")
async def get_workflows(request):
    files = []
    for dirpath, directories, file in os.walk(workflows_directory):
        for file in file:
            if (file.endswith(".json")):
                files.append(os.path.relpath(os.path.join(
                    dirpath, file), workflows_directory))
    return web.json_response(list(map(lambda f: os.path.splitext(f)[0].replace("\\", "/"), files)))


@PromptServer.instance.routes.get("/pysssss/workflows/{name:.+}")
async def get_workflow(request):
    file = os.path.abspath(os.path.join(
        workflows_directory, request.match_info["name"] + ".json"))
    if os.path.commonpath([file, workflows_directory]) != workflows_directory:
        return web.Response(status=403)

    return web.FileResponse(file)


def get_node_position(node):
    potential_pos = node.get('pos', [float('inf'), float('inf')])
    # rgthree's ImageComparer node stores its position as a dict
    if isinstance(potential_pos, dict):
        potential_pos = [potential_pos["0"], potential_pos["1"]]
    return potential_pos


def get_group_for_node(node, groups):
    node_pos = get_node_position(node)
    
    for idx, group in enumerate(groups):
        bounding = group['bounding']
        if (bounding[0] <= node_pos[0] <= bounding[0] + bounding[2] and
            bounding[1] <= node_pos[1] <= bounding[1] + bounding[3]):
            return idx, group['bounding'][:2], group.get('title', f"Group {idx}")
    
    return None, node_pos, "Ungrouped"


def sort_nodes(nodes, groups):
    return sorted(nodes, key=lambda node: (
        get_group_for_node(node, groups)[1],
        get_group_for_node(node, groups)[0] if get_group_for_node(node, groups)[0] is not None else float('inf'),
        get_node_position(node)
    ))


@PromptServer.instance.routes.post("/pysssss/workflows")
async def save_workflow(request):
    json_data = await request.json()
    file = os.path.abspath(os.path.join(
        workflows_directory, json_data["name"] + ".json"))
    if os.path.commonpath([file, workflows_directory]) != workflows_directory:
        return web.Response(status=403)

    if os.path.exists(file) and ("overwrite" not in json_data or not json_data["overwrite"]):
        return web.Response(status=409)

    sub_path = os.path.dirname(file)
    if not os.path.exists(sub_path):
        os.makedirs(sub_path)

    # Sort the workflow data
    workflow = json_data["workflow"]

    object_info_file = os.path.join("object_info.json")
    with open(object_info_file, "r") as f:
        object_info = json.load(f)

    pruned_object_info = curie.tools.update_workflow.prune_object_info(workflow, object_info)
    workflow["object_info"] = pruned_object_info
    
    # Sort nodes based on their group and position
    workflow["nodes"] = sort_nodes(workflow["nodes"], workflow.get("groups", []))

    # Save the main workflow file
    with open(file, "w") as f:
        json.dump(workflow, f, indent=4)

    logging.info(f"Saved workflow to {file}")

    # Create backups
    backup_dir = os.path.join(workflows_directory, "bak")
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    basename = os.path.splitext(os.path.basename(file))[0]
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    workflow_backup_file = os.path.join(backup_dir, f"{basename}.{timestamp}.json")
    with open(workflow_backup_file, "w") as f:
        json.dump(workflow, f, indent=4)
        
    # Clean up old backups
    clean_up_backups(backup_dir)

    return web.Response(status=201)


def clean_up_backups(backup_dir):
    # Get all .json files in the backup directory
    all_files = glob.glob(os.path.join(backup_dir, "*.json"))
    
    # Extract unique basenames using a set
    basenames = set()
    for file in all_files:
        parts = os.path.basename(file).split('.')
        if len(parts) >= 3:
            basenames.add(parts[0])
    
    for basename in basenames:
        # Get all files for this basename
        basename_files = [f for f in all_files if os.path.basename(f).startswith(f"{basename}.")]
        
        # Extract unique basename.date combinations
        unique_dates = set()
        for file in basename_files:
            parts = os.path.basename(file).split('.')
            if len(parts) >= 3:
                unique_dates.add(f"{parts[0]}.{parts[1]}")
        
        # Sort unique basename.date combinations (newest first)
        sorted_dates = sorted(list(unique_dates), key=lambda x: x.split('.')[-1], reverse=True)
        
        # Keep only the 10 most recent backup sets
        for old_date in sorted_dates[10:]:
            for old_backup in [f for f in basename_files if f.startswith(os.path.join(backup_dir, old_date))]:
                os.remove(old_backup)
