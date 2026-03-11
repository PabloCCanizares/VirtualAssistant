import sys
from types import ModuleType

from ai import config


class _DummyOpenAI:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _DummyGemini:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _DummyGroq:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


def _disable_env_file_load(monkeypatch):
    monkeypatch.setattr(config, "load_env", lambda *args, **kwargs: None)


def _clear_provider_env(monkeypatch):
    for key in (
        "LLM_PROVIDER",
        "AI_PROVIDER",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "DEEP_SEARCH_ENABLED",
        "DEEP_SEARCH_PROVIDER",
        "DEEP_SEARCH_API_KEY",
        "DEEP_SEARCH_MAX_RESULTS",
        "DEEP_SEARCH_TIMEOUT_SECONDS",
        "DEEP_SEARCH_MAX_SOURCES",
        "DEEP_SEARCH_MODE_DEFAULT",
        "DEFAULT_USER_ID",
    ):
        monkeypatch.delenv(key, raising=False)


def _install_mock_provider_modules(monkeypatch):
    openai_module = ModuleType("langchain_openai")
    setattr(openai_module, "ChatOpenAI", _DummyOpenAI)

    gemini_module = ModuleType("langchain_google_genai")
    setattr(gemini_module, "ChatGoogleGenerativeAI", _DummyGemini)

    groq_module = ModuleType("langchain_groq")
    setattr(groq_module, "ChatGroq", _DummyGroq)

    monkeypatch.setitem(sys.modules, "langchain_openai", openai_module)
    monkeypatch.setitem(sys.modules, "langchain_google_genai", gemini_module)
    monkeypatch.setitem(sys.modules, "langchain_groq", groq_module)


def test_get_settings_accepts_groq_provider(monkeypatch):
    _disable_env_file_load(monkeypatch)
    _clear_provider_env(monkeypatch)

    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("GROQ_MODEL", "llama-test")

    settings = config.get_settings()

    assert settings.llm_provider == "groq"
    assert settings.groq_api_key == "groq-key"
    assert settings.groq_model == "llama-test"


def test_get_settings_ignores_ai_provider_and_defaults_to_openai(monkeypatch):
    _disable_env_file_load(monkeypatch)
    _clear_provider_env(monkeypatch)

    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_PROVIDER", "invalid-provider")

    settings = config.get_settings()

    assert settings.llm_provider == "openai"


def test_deep_search_defaults_and_clamping(monkeypatch):
    _disable_env_file_load(monkeypatch)
    _clear_provider_env(monkeypatch)

    monkeypatch.setenv("DEEP_SEARCH_ENABLED", "yes")
    monkeypatch.setenv("DEEP_SEARCH_PROVIDER", "unknown")
    monkeypatch.setenv("DEEP_SEARCH_MAX_RESULTS", "abc")
    monkeypatch.setenv("DEEP_SEARCH_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("DEEP_SEARCH_MAX_SOURCES", "99")
    monkeypatch.setenv("DEEP_SEARCH_MODE_DEFAULT", "invalid")

    settings = config.get_settings()
    deep_cfg = config.get_deep_search_config(settings)

    assert settings.deep_search_enabled is True
    assert settings.deep_search_provider == "tavily"
    assert settings.deep_search_max_results == 8
    assert settings.deep_search_timeout_seconds == 3
    assert settings.deep_search_max_sources == 12
    assert settings.deep_search_mode_default == "auto"
    assert deep_cfg.provider == "tavily"
    assert deep_cfg.mode_default == "auto"


def test_build_llm_selects_expected_provider(monkeypatch):
    _disable_env_file_load(monkeypatch)
    _clear_provider_env(monkeypatch)
    _install_mock_provider_modules(monkeypatch)

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    llm_openai = config.build_llm()
    assert isinstance(llm_openai, _DummyOpenAI)
    assert llm_openai.kwargs["model"] == "gpt-test"

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    llm_gemini = config.build_llm()
    assert isinstance(llm_gemini, _DummyGemini)
    assert llm_gemini.kwargs["model"] == "gemini-test"

    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_MODEL", "groq-test")
    llm_groq = config.build_llm()
    assert isinstance(llm_groq, _DummyGroq)
    assert llm_groq.kwargs["model"] == "groq-test"
