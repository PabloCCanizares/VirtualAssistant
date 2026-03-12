from ai.agents.writer import writer_node


def _state_with_sources():
    return {
        "messages": [],
        "deep_research_notes": "Notas de investigacion profunda",
        "deep_research_sources": [
            {
                "title": "Fuente A",
                "url": "https://a.example.com",
                "snippet": "detalle A",
            },
            {
                "title": "Fuente B",
                "url": "https://b.example.com",
                "snippet": "detalle B",
            },
        ],
    }


def test_writer_appends_sources_when_missing(monkeypatch):
    monkeypatch.setattr("ai.agents.writer.invoke_with_retry", lambda *args, **kwargs: "Respuesta principal")
    result = writer_node(_state_with_sources(), llm=object())

    draft = result["draft_response"]
    assert "Respuesta principal" in draft
    assert "Fuentes:" in draft
    assert "https://a.example.com" in draft
    assert "https://b.example.com" in draft


def test_writer_keeps_existing_source_urls_without_dup(monkeypatch):
    monkeypatch.setattr(
        "ai.agents.writer.invoke_with_retry",
        lambda *args, **kwargs: (
            "Respuesta principal\n\nFuentes:\n"
            "- [1] Fuente A - https://a.example.com\n"
            "- [2] Fuente B - https://b.example.com"
        ),
    )
    result = writer_node(_state_with_sources(), llm=object())

    draft = result["draft_response"]
    assert draft.count("https://a.example.com") == 1
    assert draft.count("https://b.example.com") == 1


def test_writer_without_sources_does_not_add_block(monkeypatch):
    monkeypatch.setattr("ai.agents.writer.invoke_with_retry", lambda *args, **kwargs: "Respuesta sin fuentes")
    result = writer_node({"messages": [], "research_notes": "Notas"}, llm=object())
    draft = result["draft_response"]

    assert draft == "Respuesta sin fuentes"
