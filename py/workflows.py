import glob
import inspect
import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime

import requests

import curie.tools.update_workflow as update_workflow
import server


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

    object_info = server.server_get_object_info()

    pruned_object_info = update_workflow.prune_object_info(workflow, object_info)
    workflow["object_info"] = pruned_object_info
    
    # Sort nodes based on their group and position
    workflow["nodes"] = update_workflow.sort_nodes(workflow["nodes"], workflow.get("groups", []))

    # Save the workflow with backup
    update_workflow.save_workflow_with_backup(workflow, file, "on_save")

    return web.Response(status=201)
