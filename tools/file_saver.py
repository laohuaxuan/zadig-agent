import base64
import json
import os
import pickle
import shutil
from pathlib import Path
from typing import Any, Optional, Sequence

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)


def resolve_checkpoints_path() -> str:
    env = os.environ.get("CHECKPOINTS_DIR", "").strip()
    if env:
        return env
    root = Path(__file__).resolve().parents[1]
    return str(root / "checkpoints")


def has_checkpoint(thread_id: str | int, *, base_path: str | None = None) -> bool:
    root = Path(base_path or resolve_checkpoints_path()) / str(thread_id)
    if not root.is_dir():
        return False
    return any(root.glob("*.json"))


def clear_thread_checkpoints(thread_id: str | int, *, base_path: str | None = None) -> None:
    root = Path(base_path or resolve_checkpoints_path()) / str(thread_id)
    if root.is_dir():
        shutil.rmtree(root)


class FileSaver(BaseCheckpointSaver[str]):
    def __init__(self, base_path: str | None = None):
        super().__init__()
        self.base_path = base_path or resolve_checkpoints_path()
        os.makedirs(self.base_path, exist_ok=True)

    def _get_checkpoint_path(self, thread_id, checkpoint_id):
        dir_path = os.path.join(self.base_path, str(thread_id))
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, checkpoint_id + ".json")
        return file_path

    def _serialize_checkpoint(self, data) -> str:
        pickled = pickle.dumps(data)
        return base64.b64encode(pickled).decode("utf-8")

    def _deserialize_data(self, data):
        decoded = base64.b64decode(data)
        return pickle.loads(decoded)

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]

        dir_path = Path(self.base_path) / str(thread_id)
        if not dir_path.is_dir():
            return None
        checkpoint_files = list(dir_path.glob("*.json"))
        checkpoint_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        if len(checkpoint_files) > 0:
            latest_checkpoint = checkpoint_files[0]
            checkpoint_id = latest_checkpoint.stem
            checkpoint_file_path = self._get_checkpoint_path(thread_id, checkpoint_id)
            with open(checkpoint_file_path, "r", encoding="utf-8") as checkpoint_file:
                data = json.load(checkpoint_file)
            checkpoint = self._deserialize_data(data["checkpoint"])
            metadata = self._deserialize_data(data["metadata"])
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
        return None

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint["id"]
        checkpoint_path = self._get_checkpoint_path(thread_id, checkpoint_id)

        checkpoint_data = {
            "checkpoint": self._serialize_checkpoint(checkpoint),
            "metadata": self._serialize_checkpoint(metadata),
        }
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)

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
        return None

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

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        return self.put_writes(config, writes, task_id, task_path)
