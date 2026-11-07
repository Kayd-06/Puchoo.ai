"""Validated, stateless clarification choices; never erase the original filters."""
from apps.core.llm_client import question_clarification
import re


def resolve_clarifications(schema: str, question: str, answers: list[dict]):
    """Replay only choices actually offered for the current scoped question.

    Choices requesting rules are not rules. Return a new actionable instruction
    rather than executing with guessed thresholds or resubmitting the same choice.
    """
    clarification = question_clarification(schema, question)
    for index, answer in enumerate(answers):
        if (not clarification or answer["reason"] != clarification["reason"]
                or answer["choice"] not in clarification.get("suggestions", [])):
            raise ValueError("Clarification no longer matches this question")
        reason, choice = answer["reason"], answer["choice"]
        next_detail = None
        if reason == "missing_time_definition" and choice == "Use calendar year instead":
            # Change only the explicitly resolved calendar, not year/class/region.
            question = re.sub(r"\bfiscal\s+(year|quarter|month)\b", r"calendar \1", question, flags=re.I)
        elif reason == "ambiguous_education_metric":
            question += "\nSelected metric: " + choice.removeprefix("Use ")
            next_detail = ("education_rule_required", "State the exact threshold or comparison and time period for the selected metric. Edit the question using those rules instead of 'doing well' or 'needs attention'; keep your original class/date filters.")
        elif reason == "missing_policy_definition":
            next_detail = ("policy_rules_required", "Provide the institution's exact rules using the selected fields. Rephrase the question as those explicit conditions; choosing fields alone does not define eligibility.")
        elif reason == "missing_classification_factor_rules" and choice.startswith("Include fees"):
            next_detail = ("classification_rules_required", "Provide the scoring rules for marks, attendance, fees and enrollment, including thresholds and comparison periods. These rules cannot be inferred from a field choice.")
        elif reason == "concept_not_in_data":
            if choice == "Show available tables and fields":
                next_detail = ("available_schema", "Available tables and fields:\n" + schema)
            else:
                next_detail = ("concept_definition_required", "Replace the undefined business concept with an explicit calculation using the available column names, keeping your original filters. No formula has been inferred.")
        else:
            definition = "Rank by transaction count" if choice == "Rank by number of transactions" else choice
            question += "\nUser-selected definition: " + definition
        if next_detail:
            if index != len(answers) - 1:
                raise ValueError("Additional rules must be supplied in the question")
            clarification = {"reason": next_detail[0], "message": next_detail[1], "suggestions": []}
        else:
            clarification = question_clarification(schema, question)
            if clarification and clarification["reason"] == reason:
                # No blanket bypass: a new detail request cannot authorize SQL.
                clarification = {"reason": "additional_definition_required", "message": "Please rewrite the question with the exact selected definition and any remaining thresholds or periods. Keep all original filters.", "suggestions": []}
    return question, clarification
