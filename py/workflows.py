import logging
from server import PromptServer
from aiohttp import web
import os
import inspect
import json
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pysssss

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
    
    # Sort nodes based on their group and position
    workflow["nodes"] = sort_nodes(workflow["nodes"], workflow.get("groups", []))

    with open(file, "w") as f:
        json.dump(workflow, f, indent=4)

    logging.info(f"Saved workflow to {file}")
    return web.Response(status=201)
