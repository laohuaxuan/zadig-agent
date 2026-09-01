import os, json
from pathlib import Path
from typing import Optional, Sequence, Any
import pickle, base64

from langgraph.checkpoint.memory import BaseCheckpointSaver
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import CheckpointTuple, BaseCheckpointSaver, CheckpointMetadata, ChannelVersions, Checkpoint

class FileSaver(BaseCheckpointSaver[str]):
    def __init__(self, base_path: str = "../checkpoints"):
        super().__init__()
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

    #创建存储路径
    def _get_checkpoint_path(self, thread_id, checkpoint_id):
        dir_path = os.path.join(self.base_path, thread_id)
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, checkpoint_id + ".json")
        return file_path
    
    #序列化checkpoint数据
    def _serialize_checkpoint(self, data) -> str:
        pickled = pickle.dumps(data)
        return base64.b64encode(pickled).decode("utf-8")
    
    #反序列化checkpoint数据
    def _deserialize_data(self, data):
        decoded = base64.b64decode(data)
        return pickle.loads(decoded)
    
    #获取checkpoint
    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        # 1. 找到正确的checkpoint文件路径
        thread_id = config["configurable"]["thread_id"]

        # 2. 读取checkpoint文件内容
        dir_path = Path(self.base_path) / str(thread_id)
        if not dir_path.is_dir():
            return None
        checkpoint_files = list(dir_path.glob("*.json"))
        # 按修改时间倒序，取最新一份（数据最全）
        checkpoint_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        if len(checkpoint_files) > 0:
            latest_checkpoint = checkpoint_files[0]
            checkpoint_id = latest_checkpoint.stem
            checkpoint_file_path = self._get_checkpoint_path(thread_id, checkpoint_id)
            # 3. 对文件内容进行反序列化
            with open(checkpoint_file_path, "r", encoding="utf-8") as checkpoint_file:
                data = json.load(checkpoint_file)
            checkpoint = self._deserialize_data(data["checkpoint"])
            metadata = self._deserialize_data(data["metadata"])
            # 4. 返回checkpoint对象
            return CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": checkpoint_id,
                    }
                },
                checkpoint=checkpoint,
                metadata=metadata,
            )
        else:
            return None

    #保存checkpoint数据
    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        pass
        # 生成存储的JSON文件路径
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint["id"]
        checkpoint_path = self._get_checkpoint_path(thread_id, checkpoint_id)

        # 将Checkpoint进行序列化
        checkpoint_data = {
            "checkpoint": self._serialize_checkpoint(checkpoint),
            "metadata": self._serialize_checkpoint(metadata),
        }
        # 将Checkpoint存储到文件系统
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)

        # 生成返回值
        # return config
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        print("put_writes")

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self.get_tuple(config)
    
    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config: RunnableConfig, writes: Sequence[tuple[str, Any]], task_id: str, task_path: str = "") -> None:
        return self.put_writes(config, writes, task_id, task_path)

# if __name__ == '__main__':
#     memory = FileSaver()

#     agent = create_react_agent(
#         model=openrouter_llm,
#         tools=file_tools,
#         checkpointer=memory,
#         debug=True,
#     )

#     config = RunnableConfig(configurable={"thread_id": 1})

#     while True:
#         user_input = input("用户：")
#         if user_input.lower() == "exit":
#             break
#         resp = agent.invoke(input={"messages": user_input}, config=config)
#         # print(resp)
#         print("助理：" + resp['messages'][-1].content)
#         print()