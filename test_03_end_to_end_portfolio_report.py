import os
import json
import asyncio


def setup_env():
    os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    os.environ.setdefault("SUPABASE_BUCKET_NAME", "portfolio-files")
    os.environ.setdefault("SUPABASE_BASE_PREFIX", "Graficos")
    os.environ.setdefault("GEMINI_API_KEY", "test-key")


class _FakeStorageBucket:
    def __init__(self, files):
        self._files = files
    def list(self, prefix):
        filtered = []
        for f in self._files:
            if f.startswith(prefix + "/"):
                name = f[len(prefix) + 1:]
                if "/" in name:
                    continue
                filtered.append({"name": name})
        return filtered
    def download(self, path):
        if path.endswith(".json"):
            return b'{"ok": true, "source": "json"}'
        if path.endswith(".md"):
            return b"# Markdown de prueba"
        if path.endswith(".png"):
            return b"PNG_BYTES"
        raise FileNotFoundError(path)


class _FakeSupabaseClient:
    def __init__(self, files):
        class _Storage:
            def __init__(self, files):
                self._files = files
            def from_(self, bucket):
                return _FakeStorageBucket(self._files)
        self.storage = _Storage(files)


class _FakeGenAIResponse:
    def __init__(self, parsed=None, text=None):
        self.parsed = parsed
        self.text = text


class _FakeGenAioModels:
    async def generate_content(self, model, contents, config):
        # Inspecciona el CONTEXT_JSON y devuelve un Report mínimo
        from models import Report, DocumentMetadata, ContentItem
        report = Report(
            fileName="Informe_Estrategico_Portafolio_Test.pdf",
            document=DocumentMetadata(title="Informe Estratégico de Portafolio", author="Tester", subject="E2E"),
            content=[
                ContentItem(type="header1", text="Informe Estratégico de Portafolio"),
                ContentItem(type="paragraph", text="Resumen de prueba"),
                ContentItem(type="image", path="portfolio_growth.png", caption="Figura 1")
            ],
        )
        return _FakeGenAIResponse(parsed=report)


class _FakeGenAIClient:
    def __init__(self):
        class _Aio:
            def __init__(self):
                class _Models:
                    async def generate_content(inner, model, contents, config):
                        return await _FakeGenAioModels().generate_content(model, contents, config)
                self.models = _Models()
        self.aio = _Aio()


async def run_test():
    setup_env()
    from agent_service import chat_service
    from models import PortfolioReportRequest

    # Fake Supabase
    files = [
        "Graficos/portfolio_growth.png",
        "Graficos/notas.md",
        "Graficos/metrics.json",
    ]
    chat_service.supabase = _FakeSupabaseClient(files)
    chat_service.supabase_bucket = os.environ.get("SUPABASE_BUCKET_NAME", "portfolio-files")
    chat_service.supabase_prefix = os.environ.get("SUPABASE_BASE_PREFIX", "Graficos")

    # Fake Gemini
    chat_service.client = _FakeGenAIClient()

    req = PortfolioReportRequest(
        model_preference="pro",
        context={"metrics": {"sharpe": "1.67"}}
    )
    result = await chat_service.ejecutar_generacion_informe_portafolio(req)

    assert "report" in result, "Debe contener 'report'"
    rep = result["report"]
    assert rep["fileName"].endswith(".pdf")
    assert isinstance(rep.get("content"), list) and len(rep["content"]) >= 1
    types = [c.get("type") for c in rep["content"]]
    assert "paragraph" in types, "Debe incluir al menos un párrafo"

    print("OK: flujo E2E con lectura de Storage y salida Report válida")
    print(json.dumps(result, ensure_ascii=False)[:500] + "...")


if __name__ == "__main__":
    asyncio.run(run_test())


