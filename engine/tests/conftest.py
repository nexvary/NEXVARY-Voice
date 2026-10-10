import pytest

from voice_engine.api import app, get_translator


class FakeTranslator:
    def translate(self, text: str, source: str, target: str) -> str:
        return f"[{source}>{target}] {text}"


@pytest.fixture()
def fake_engine():
    app.dependency_overrides[get_translator] = lambda: FakeTranslator()
    yield
    app.dependency_overrides.clear()
