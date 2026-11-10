"""配置读取冒烟测试（M0 runbook §0.3 验收项：`pytest tests/test_config.py` 过）。

只验证"配置骨架生效"，不要求任何外部服务在线：
- .env / 默认值能读出类型正确的模型配置；
- 路径常量与仓库结构一致；
- 消融档位 A–F 常量完整。
"""

from doclens.config import ABLATION_TIERS, DATA_DIR, PROJECT_ROOT, settings


def test_model_settings_load() -> None:
    """模型配置键可读、类型正确、默认值符合 spec。"""
    assert isinstance(settings.embed_dimensions, int)
    assert settings.embed_dimensions == 2048
    assert settings.embed_model.startswith("doubao")
    assert settings.gen_model.startswith("doubao")
    assert settings.ctx_model.startswith("deepseek")
    assert settings.ark_base_url.startswith("https://ark.")


def test_storage_urls_configured() -> None:
    """存储地址两端口齐备（容器侧 127.0.0.1，Windows 侧服务器 IP，均合法）。"""
    assert "3306" in settings.mysql_url
    assert settings.mysql_url.startswith("mysql+pymysql://")
    assert "6333" in settings.qdrant_url
    assert settings.qdrant_url.startswith("http")


def test_path_constants() -> None:
    """路径常量指向仓库真实结构（pathlib 跨平台，无写死路径）。"""
    assert (PROJECT_ROOT / ".env.example").exists()
    assert DATA_DIR.exists()
    assert PROJECT_ROOT == DATA_DIR.parent


def test_ablation_tiers_a_to_f() -> None:
    """消融阶梯 A–F 六档齐全，每档说明非空（PRD §7.1）。"""
    assert list(ABLATION_TIERS.keys()) == ["A", "B", "C", "D", "E", "F"]
    assert all(desc.strip() for desc in ABLATION_TIERS.values())
