from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"

_cache: dict | None = None
_mtime: float | None = None


def load_config() -> dict:
    """读取 config.yaml；文件 mtime 变化时自动重新加载。"""
    global _cache, _mtime
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"缺少配置文件 {CONFIG_PATH}，请复制 config.example.yaml 为 config.yaml 后填写密钥"
        )
    mtime = CONFIG_PATH.stat().st_mtime
    if _cache is not None and _mtime == mtime:
        return _cache
    with CONFIG_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("config.yaml 格式无效，根节点必须是映射")
    reloaded = _cache is not None
    _cache = data
    _mtime = mtime
    if reloaded:
        print(f"已热加载配置：{CONFIG_PATH}")
    return _cache


def openrouter_config() -> dict:
    cfg = load_config().get("openrouter") or {}
    if not isinstance(cfg, dict):
        raise ValueError("config.yaml 中 openrouter 必须是映射")
    api_key = str(cfg.get("api_key") or "").strip()
    if not api_key or api_key == "YOUR_OPENROUTER_API_KEY":
        raise ValueError("请在 config.yaml 的 openrouter.api_key 中填写 OpenRouter API Key")
    model = str(cfg.get("model") or "").strip()
    base_url = str(cfg.get("base_url") or "https://openrouter.ai/api/v1").strip()
    if not model:
        raise ValueError("请在 config.yaml 的 openrouter.model 中填写模型名称")
    return {"api_key": api_key, "model": model, "base_url": base_url}


def zadig_config() -> dict:
    cfg = load_config().get("zadig") or {}
    if not isinstance(cfg, dict):
        raise ValueError("config.yaml 中 zadig 必须是映射")
    base_url = str(cfg.get("base_url") or "").strip().rstrip("/")
    api_token = str(cfg.get("api_token") or "").strip()
    if not base_url or base_url in {"https://your.zadig.com", "http://your.zadig.com"}:
        raise ValueError("请在 config.yaml 的 zadig.base_url 中填写 Zadig 访问地址")
    if not api_token or api_token == "YOUR_ZADIG_API_TOKEN":
        raise ValueError("请在 config.yaml 的 zadig.api_token 中填写 Zadig API Token")
    return {"base_url": base_url, "api_token": api_token}
