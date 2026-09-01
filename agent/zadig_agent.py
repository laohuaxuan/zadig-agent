import asyncio
import sys
import time
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from model.openrouter import get_openrouter_llm
from tools.file_saver import FileSaver
from tools.file_tools import file_tools
from tools.build import get_stdio_tools as get_build_stdio_tools
from tools.cluster import get_stdio_tools as get_cluster_stdio_tools
from tools.collaboration import get_stdio_tools as get_collaboration_stdio_tools
from tools.environment import get_stdio_tools as get_environment_stdio_tools
from tools.policy import get_stdio_tools as get_policy_stdio_tools
from tools.project import get_stdio_tools as get_project_stdio_tools
from tools.registry import get_stdio_tools as get_registry_stdio_tools
from tools.services import get_stdio_tools as get_services_stdio_tools
from tools.system import get_stdio_tools as get_system_stdio_tools
from tools.templates import get_stdio_tools as get_templates_stdio_tools
from tools.users import get_stdio_tools as get_users_stdio_tools
from tools.workflows import get_stdio_tools as get_workflows_stdio_tools

def format_debug_output(step_name: str, content: str, is_tool_call: bool = False) -> None:
    if is_tool_call:
        print(f"🛠️【工具调用】{step_name}")
        print("-"*40)
        print(content.strip())
        print("-"*40)
    else:
        print(f"💡【{step_name}】")
        print("-"*40)
        print(content.strip())
        print("-"*40)

async def run_agent():
    memory = FileSaver()
    # tools
    project_tools = await get_project_stdio_tools()
    environment_tools = await get_environment_stdio_tools()
    services_tools = await get_services_stdio_tools()
    build_tools = await get_build_stdio_tools()
    workflows_tools = await get_workflows_stdio_tools()
    cluster_tools = await get_cluster_stdio_tools()
    registry_tools = await get_registry_stdio_tools()
    templates_tools = await get_templates_stdio_tools()
    policy_tools = await get_policy_stdio_tools()
    users_tools = await get_users_stdio_tools()
    system_tools = await get_system_stdio_tools()
    collaboration_tools = await get_collaboration_stdio_tools()
    tools = [
        *file_tools,
        *project_tools,
        *environment_tools,
        *services_tools,
        *build_tools,
        *workflows_tools,
        *cluster_tools,
        *registry_tools,
        *templates_tools,
        *policy_tools,
        *users_tools,
        *system_tools,
        *collaboration_tools,
    ]

    prompt = PromptTemplate.from_template("""
# 角色
你是一名优秀的运维工程师，你的名字叫做{name}，你非常熟悉Zadig发布系统CICD相关知识，你可以根据用户的需求使用工具执行任务。
""")

    def select_model(state, runtime):
        return get_openrouter_llm().bind_tools(tools)

    agent = create_react_agent(
        model=select_model,
        tools=tools,
        checkpointer=memory,
        debug=False,
        prompt=prompt.format(name="zadig_bot")
    )

    config = RunnableConfig(configurable={"thread_id": 6}, recursion_limit=100)

    while True:
        user_input = input("用户：")
        if user_input.lower() == "exit":
            break
        print("\n🤖 助手正在思考和处理...")
        print("="*60)

        # resp = await agent.ainvoke(input={"messages": user_input}, config=config)
        # print("助理:", resp['messages'][-1].content)
        # print()
        iteration_count = 0
        start_time = time.time()
        last_tool_time = start_time
        async for chunk in agent.astream(input={"messages": user_input}, config=config):
            iteration_count += 1
            print(f"\n第 {iteration_count} 步执行：")
            print("-"*30)
            # print(chunk)
            # print("助理：" + resp['messages'][-1].content)
            items = chunk.items()
            for node_name, node_output in items:
                if "messages" in node_output:
                    for msg in node_output["messages"]:
                        if isinstance(msg, AIMessage):
                            if msg.content:
                                format_debug_output("AI思考", msg.content)
                            else:
                                for tool in msg.tool_calls:
                                    format_debug_output("工具调用", f"{tool['name']}: {tool['args']}")

                        elif isinstance(msg, ToolMessage):
                            tool_name = getattr(msg, "name", "unknown")
                            tool_content = msg.content

                            current_time = time.time()
                            tool_duration = current_time - last_tool_time
                            last_tool_time = current_time

                            tool_result = f"""🔧工具：{tool_name}
📮结果：
{tool_content}
✅状态：执行完成，可以开始下一个任务
⏱ 执行时间：{tool_duration: .2f}秒"""
                            format_debug_output("工具执行结果", tool_result, is_tool_call=True)
                        else:
                            format_debug_output("未实现", f"暂未实现的打印内容：{chunk}")
if __name__ == "__main__":
    asyncio.run(run_agent())