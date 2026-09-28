import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.pipeline import Pipeline  # noqa: E402
from app.understand.orchestrator import AIQueryOrchestrator, QueryPlan  # noqa: E402
from contracts.analysis import CitationStatus  # noqa: E402
from contracts.requirement import InputPayload  # noqa: E402


class OfflineLLM:
    available = False


class TextInput:
    @staticmethod
    def read_text(text):
        return InputPayload(source="text", text=text, richness="spec_only")


class EnglishOnly:
    @staticmethod
    def detect(_text):
        return "en"


class HindiMock(EnglishOnly):
    @staticmethod
    def detect(_text):
        return "hi"

    @staticmethod
    def to_english(text, _source):
        return text, "hi"

    @staticmethod
    def from_english_many(texts, target):
        return [f"[{target}] {text}" for text in texts]


def make_pipeline():
    pipeline = Pipeline.__new__(Pipeline)
    pipeline.input_handler = TextInput()
    pipeline.language = EnglishOnly()
    pipeline.orchestrator = AIQueryOrchestrator(llm=OfflineLLM())
    return pipeline


def test_general_question_returns_without_constructing_retrieval_engine():
    pipeline = make_pipeline()

    result = pipeline.analyze(text="What is the difference between IS and ISO?")

    assert result.plan.intent == "general_question"
    assert result.recommendation.primary is None
    assert "Indian Standard" in result.recommendation.explanation
    assert not hasattr(pipeline, "engine")


def test_general_question_uses_existing_localization_path():
    pipeline = make_pipeline()
    pipeline.language = HindiMock()

    result = pipeline.analyze(text="What is the difference between IS and ISO?", language="auto")

    assert result.language == "hi"
    assert result.recommendation.explanation.startswith("[hi] ")


def test_exact_standard_question_uses_catalogue_resolver_only():
    pipeline = make_pipeline()
    pipeline.extractor = SimpleNamespace(_citations=lambda _text: ["IS 269:2015"])
    pipeline.resolver = SimpleNamespace(resolve=lambda _citation: SimpleNamespace(
        exists=True,
        current="IS 269:2015",
        cited_edition="IS 269:2015",
        title="Ordinary Portland Cement",
        warnings=[],
        amendments=[],
    ))

    result = pipeline.analyze(text="What is IS 269:2015?")

    assert result.plan.intent == "standard_lookup"
    assert result.recommendation.primary == "IS 269:2015"
    assert result.recommendation.primary_title == "Ordinary Portland Cement"
    assert not hasattr(pipeline, "engine")


def test_material_orchestrator_clarification_stops_before_retrieval():
    pipeline = make_pipeline()
    pipeline.orchestrator = SimpleNamespace(resolve=lambda *_args, **_kwargs: QueryPlan(
        intent="standards_recommendation",
        product="pipes",
        category="pipes_plastic",
        missing_information=["application"],
        clarification="Are the pipes for water supply, drainage, or irrigation?",
        retrieval_text="pipes",
    ))

    result = pipeline.analyze(text="Find standards for pipes")

    assert result.needs_more_info
    assert result.sufficiency.questions == [{
        "field": "application",
        "ask": "Are the pipes for water supply, drainage, or irrigation?",
    }]
    assert not hasattr(pipeline, "engine")