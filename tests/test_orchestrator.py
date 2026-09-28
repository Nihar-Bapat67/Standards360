import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.understand.orchestrator import AIQueryOrchestrator  # noqa: E402
from contracts.requirement import RequirementObject  # noqa: E402


class OfflineLLM:
    available = False


class RecordingLLM:
    available = True

    def __init__(self):
        self.calls = []

    def complete(self, system, user, **_kwargs):
        self.calls.append((system, user))
        return "BIS publishes Indian Standards."


class MisclassifyingLLM:
    available = True

    def complete_json(self, *_args, **_kwargs):
        return {"intent": "standards_recommendation", "product": "", "category": "",
                "attributes": {}, "missing_information": [], "clarification": None}


def test_short_follow_up_keeps_product_and_adds_application():
    previous = RequirementObject(
        product="PVC pipes",
        category="pipes_plastic",
        attributes={"type": "PVC", "grade": "pressure class"},
    )

    plan = AIQueryOrchestrator(llm=OfflineLLM()).resolve("Water supply", previous=previous)

    assert plan.intent == "standards_recommendation"
    assert plan.product == "PVC pipes"
    assert plan.category == "pipes_plastic"
    assert plan.attributes["type"] == "PVC"
    assert plan.attributes["application"] == "Water supply"
    assert "PVC pipes" in plan.retrieval_text
    assert "Water supply" in plan.retrieval_text


def test_unrelated_question_without_context_does_not_route_to_retrieval():
    plan = AIQueryOrchestrator(llm=OfflineLLM()).resolve("What is the difference between IS and ISO?")

    assert plan.intent == "general_question"


def test_model_cannot_route_unrelated_message_into_standards_retrieval():
    plan = AIQueryOrchestrator(llm=MisclassifyingLLM()).resolve("I am a paper manufacturer")

    assert plan.intent == "general_question"


def test_greeting_gets_short_welcome():
    llm = RecordingLLM()

    answer = AIQueryOrchestrator(llm=llm).answer_general("Hello!")

    assert answer.startswith("Hello!")
    assert llm.calls == []


def test_unrelated_question_is_redirected_without_calling_llm():
    llm = RecordingLLM()

    answer = AIQueryOrchestrator(llm=llm).answer_general("How do I bake sourdough bread?")

    assert "only questions about Indian Standards" in answer
    assert llm.calls == []


def test_unrelated_question_stays_out_of_scope_even_with_thread_history():
    llm = RecordingLLM()

    answer = AIQueryOrchestrator(llm=llm).answer_general(
        "How do I bake sourdough bread?", history=[{"role": "user", "text": "Find cement standards"}])

    assert "only questions about Indian Standards" in answer
    assert llm.calls == []


def test_short_contextual_follow_up_can_use_llm():
    llm = RecordingLLM()

    answer = AIQueryOrchestrator(llm=llm).answer_general(
        "Why?", history=[{"role": "assistant", "text": "IS 269:2015 is recommended."}])

    assert answer == "BIS publishes Indian Standards."
    assert llm.calls


def test_standards_question_uses_llm_with_domain_guardrail_prompt():
    llm = RecordingLLM()

    answer = AIQueryOrchestrator(llm=llm).answer_general("What does BIS do?")

    assert answer == "BIS publishes Indian Standards."
    assert len(llm.calls) == 1
    assert "Stay strictly within BIS/Indian Standards" in llm.calls[0][0]


def test_is_vs_iso_question_is_kept_in_scope_without_llm():
    answer = AIQueryOrchestrator(llm=OfflineLLM()).answer_general(
        "What is the difference between IS and ISO?")

    assert "ISO refers to an International Standard" in answer


def test_test_method_follow_up_keeps_prior_requirement():
    previous = RequirementObject(product="ordinary Portland cement", category="cement")

    plan = AIQueryOrchestrator(llm=OfflineLLM()).resolve("What about testing?", previous=previous)

    assert plan.intent == "test_methods"
    assert plan.product == "ordinary Portland cement"


def test_plural_tests_follow_up_routes_to_test_methods():
    previous = RequirementObject(product="ordinary Portland cement", category="cement")

    plan = AIQueryOrchestrator(llm=OfflineLLM()).resolve("What about the tests?", previous=previous)

    assert plan.intent == "test_methods"


def test_correction_does_not_inherit_stale_product_or_attributes():
    previous = RequirementObject(
        product="PVC pipes",
        category="pipes_plastic",
        attributes={"type": "PVC", "application": "water supply"},
    )

    plan = AIQueryOrchestrator(llm=OfflineLLM()).resolve(
        "Sorry, I meant stainless steel pipes for food processing", previous=previous)

    assert plan.replace_context is True
    assert plan.product == ""
    assert plan.attributes == {}
    assert "PVC pipes" not in plan.retrieval_text