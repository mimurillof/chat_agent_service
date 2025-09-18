import os
import json
import asyncio


def setup_env():
    os.environ.setdefault("GEMINI_API_KEY", "test-key")


class _FakeGenAIResponse:
    def __init__(self, parsed=None, text=None):
        self.parsed = parsed
        self.text = text


class _FakeGenAIAioModels:
    async def generate_content(self, model, contents, config):
        from models import Report, DocumentMetadata, ContentItem
        report = Report(
            fileName="Informe_Portafolio_Test.pdf",
            document=DocumentMetadata(title="Informe de Prueba", author="Agente", subject="Portafolio"),
            content=[ContentItem(type="paragraph", text="Contenido de prueba")],
        )
        return _FakeGenAIResponse(parsed=report)


class _FakeGenAIClient:
    def __init__(self):
        class _Aio:
            def __init__(self):
                class _Models:
                    async def generate_content(inner, model, contents, config):
                        return await _FakeGenAIAioModels().generate_content(model, contents, config)
                self.models = _Models()
        self.aio = _Aio()


async def run_test():
    setup_env()
    # Import después de setear env
    from agent_service import chat_service
    from models import PortfolioReportRequest

    # Parchar cliente de Gemini
    chat_service.client = _FakeGenAIClient()

    req = PortfolioReportRequest(
        model_preference="pro",
        context={"metrics": {"sharpe": "1.23"}}
    )
    result = await chat_service.ejecutar_generacion_informe_portafolio(req)

    assert isinstance(result, dict), "La salida debe ser un dict"
    assert "report" in result, "Debe incluir 'report'"
    assert result.get("model_used"), "Debe indicar el modelo utilizado"
    assert result["report"]["fileName"].endswith(".pdf"), "fileName debe ser un PDF"

    print("OK: ejecución de método del agente y esquema básico válido")
    print(json.dumps(result, ensure_ascii=False)[:400] + "...")


if __name__ == "__main__":
    asyncio.run(run_test())


