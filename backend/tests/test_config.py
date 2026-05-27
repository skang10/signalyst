from src.config import PROJECT_ROOT, Settings


def test_cors_origins_default():
    s = Settings()
    assert "http://localhost:3000" in s.cors_origins


def test_cors_origins_configurable():
    s = Settings(cors_origins=["https://app.example.com"])
    assert s.cors_origins == ["https://app.example.com"]


def test_env_file_uses_project_root():
    assert Settings.model_config["env_file"] == PROJECT_ROOT / ".env"


def test_settings_has_gpr_data_url():
    from src.config import settings

    assert (
        settings.gpr_data_url
        == "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
    )


def test_settings_has_gpr_cache_ttl_hours():
    from src.config import settings

    assert settings.gpr_cache_ttl_hours == 24


def test_blank_gpr_env_values_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("GPR_DATA_URL", "")
    monkeypatch.setenv("GPR_CACHE_TTL_HOURS", "")

    s = Settings()

    assert s.gpr_data_url == "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
    assert s.gpr_cache_ttl_hours == 24
