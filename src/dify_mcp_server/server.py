import asyncio
import json
import os
from abc import ABC

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from omegaconf import OmegaConf
import aiohttp  # 비동기 HTTP 클라이언트


class DifyAPI(ABC):
    def __init__(self, config_path, user="default_user"):
        if not config_path:
            raise ValueError("Config path not provided.")
        self.config = OmegaConf.load(config_path)

        # Dify configurations
        self.dify_base_url = self.config.dify_base_url
        self.dify_app_sks = self.config.dify_app_sks
        self.user = user

        # Dify app information
        dify_app_infos = []
        dify_app_params = []
        dify_app_metas = []
        for key in self.dify_app_sks:
            dify_app_infos.append(self.get_app_info(key))
            dify_app_params.append(self.get_app_parameters(key))
            dify_app_metas.append(self.get_app_meta(key))
        self.dify_app_infos = dify_app_infos
        self.dify_app_params = dify_app_params
        self.dify_app_metas = dify_app_metas
        self.dify_app_names = [x['name'] for x in dify_app_infos]

    async def chat_message(self, api_key, inputs={}, response_mode="streaming", conversation_id=None, user="default_user", files=None):
        url = f"{self.dify_base_url}/workflows/run"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "inputs": inputs,
            "response_mode": response_mode,
            "user": user,
        }
        if conversation_id:
            data["conversation_id"] = conversation_id

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                response.raise_for_status()

                if response_mode == "streaming":
                    async for line in response.content:
                        if line.startswith(b'data:'):
                            try:
                                yield json.loads(line[5:].decode('utf-8'))
                            except json.JSONDecodeError:
                                print(f"Error decoding JSON: {line}")
                else:
                    return await response.json()

    def get_app_info(self, api_key):
        url = f"{self.dify_base_url}/info"
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def get_app_parameters(self, api_key):
        url = f"{self.dify_base_url}/parameters"
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def get_app_meta(self, api_key):
        url = f"{self.dify_base_url}/meta"
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


config_path = os.getenv("CONFIG_PATH")
server = Server("dify_mcp_server")
dify_api = DifyAPI(config_path)


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    tools = []
    tool_names = dify_api.dify_app_names
    tool_infos = dify_api.dify_app_infos
    tool_params = dify_api.dify_app_params

    for i in range(len(tool_names)):
        app_info = tool_infos[i]

        input_schema = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        app_param = tool_params[i]
        
        if 'user_input_form' in app_param:
            TYPE_MAPPING = {
                "paragraph": "string",
                "number-input": "number",
                "select": "string"
            }

            for param in app_param['user_input_form']:
                field_type = list(param.keys())[0]
                param_info = param[field_type]
                property_name = param_info['variable']

                input_schema["properties"][property_name] = {
                    "type": TYPE_MAPPING.get(field_type, "string"),
                    "description": param_info.get('label', ''),
                    "default": param_info.get('default', "")
                }
                if param_info.get('required', False):
                    input_schema["required"].append(property_name)

        tools.append(
            types.Tool(
                name=app_info['name'],
                description=app_info['description'],
                inputSchema=input_schema,
            )
        )
    return tools


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    tool_names = dify_api.dify_app_names

    if name not in tool_names:
        raise ValueError(f"Unknown tool: {name}")

    tool_idx = tool_names.index(name)
    tool_sk = dify_api.dify_app_sks[tool_idx]

    try:
        responses = dify_api.chat_message(tool_sk, arguments)
        
        outputs = {}
        
        async for res in responses:
            if res['event'] == 'workflow_started':
                print(f"[DEBUG] Workflow started: Task ID {res['task_id']}")
            elif res['event'] == 'message':
                print(f"[DEBUG] Intermediate message: {res['message']}")
            elif res['event'] == 'workflow_finished':
                outputs.update(res['data']['outputs'])
            elif res['event'] == 'error':
                raise Exception(res['data'])

    except Exception as e:
        error_msg = f"Error occurred: {str(e)}"
        return [types.TextContent(type="text", text=error_msg)]

    return [
        types.TextContent(type="text", text=value) for value in outputs.values()
    ]


@server.list_resources()
async def handle_list_resources():
    # Placeholder implementation for resources/list RPC method.
    return []


@server.list_prompts()
async def handle_list_prompts():
    # Placeholder implementation for prompts/list RPC method.
    return []


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="dify_mcp_server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
                protocol_version="2024-11-05",
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
