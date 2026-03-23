"""term_correct — MCP tool for user-initiated terminology corrections.

Allows users to explicitly correct terminology mappings in the project glossary.
Integrated with the glossary system to prioritize user corrections over domain packs.
"""

import structlog

from src.glossary.term_store import ProjectGlossary

logger = structlog.get_logger(__name__)


async def term_correct(
    source_term: str,
    correct_translation: str,
    wrong_translation: str = "",
    context: str = "",
) -> dict:
    """Correct a terminology mapping in the project glossary.

    This tool allows domain experts and PMs to explicitly correct how code
    terminology is translated to business language. Corrections are stored
    with highest priority and override domain pack definitions.

    Args:
        source_term: The original code term to be corrected (e.g., "idempotent").
        correct_translation: The correct Chinese translation or business term
            (e.g., "幂等操作").
        wrong_translation: Optional. The incorrect translation that was previously
            used (for documentation purposes).
        context: Optional. Context where this correction applies (e.g., "API response",
            "payment reconciliation").

    Returns:
        On success:
            {
                "status": "ok",
                "message": "Correction recorded and active",
                "affected_scope": "当前项目"
            }
        On failure:
            {
                "status": "error",
                "error": "Missing required field: source_term",
                "hint": "Please provide both source_term and correct_translation"
            }
    """
    logger.info(
        "tool.term_correct.called",
        source_term=source_term,
        context=context,
        has_wrong_translation=bool(wrong_translation),
    )

    # Validate required fields
    if not source_term or not isinstance(source_term, str) or source_term.strip() == "":
        logger.error("term_correct.validation.source_term_missing")
        return {
            "status": "error",
            "error": "Missing required field: source_term",
            "hint": "Please provide a non-empty source_term (the code term to be corrected)",
        }

    if not correct_translation or not isinstance(correct_translation, str) or correct_translation.strip() == "":
        logger.error("term_correct.validation.correct_translation_missing")
        return {
            "status": "error",
            "error": "Missing required field: correct_translation",
            "hint": "Please provide a non-empty correct_translation (the business term or Chinese translation)",
        }

    try:
        # Get or create glossary for current project
        # Note: In MCP context, we don't have repo_url from the tool call
        # We use a placeholder that will be resolved in the actual integration
        # For now, we use a default repo identifier
        glossary = ProjectGlossary("codebook://current_project")

        # Add the correction to the glossary
        success = glossary.add_correction(
            source_term=source_term.strip(),
            target_phrase=correct_translation.strip(),
            context=context.strip() if context else "",
            domain="general",  # User corrections are general by default
        )

        if not success:
            logger.warning(
                "term_correct.add_correction_failed",
                source_term=source_term,
            )
            return {
                "status": "error",
                "error": "Failed to store correction in glossary",
                "hint": "There may be a persistence issue. Check that ~/.codebook/memory/ is accessible.",
            }

        logger.info(
            "term_correct.success",
            source_term=source_term,
            affected_scope="当前项目",
        )

        # Build success message
        message_parts = [
            f"术语纠正已记录: 「{source_term.strip()}」→ 「{correct_translation.strip()}」"
        ]
        if wrong_translation:
            message_parts.append(f"（之前的错误翻译: 「{wrong_translation.strip()}」）")
        if context:
            message_parts.append(f"应用场景: {context.strip()}")

        return {
            "status": "ok",
            "message": "。".join(message_parts) + "。本纠正已在当前项目全局激活，后续 scan_repo/read_chapter 等工具会优先使用该纠正。",
            "affected_scope": "当前项目",
        }

    except Exception as e:
        logger.exception(
            "term_correct.unexpected_error",
            source_term=source_term,
            error=str(e),
        )
        return {
            "status": "error",
            "error": f"Unexpected error: {str(e)}",
            "hint": "This may be a system issue. Check server logs for details.",
        }
