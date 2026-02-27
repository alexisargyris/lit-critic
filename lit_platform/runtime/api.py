"""
API interaction layer for the lit-critic system.
Handles LLM calls for lenses and coordinator via the provider-agnostic LLMClient.
"""

import asyncio
import json
import logging

from lit_platform.session_state_machine import apply_re_evaluation_result

from .llm import LLMClient
from .config import MODEL, MAX_TOKENS, COORDINATOR_MAX_TOKENS
from .models import Finding, LensResult, CoordinatorError
from .lens_preferences import normalize_lens_preferences, rerank_coordinated_findings
from .prompts import (
    get_lens_prompt, get_coordinator_prompt, get_coordinator_chunk_prompt,
    get_re_evaluation_prompt, COORDINATOR_TOOL, LENS_GROUPS,
)

logger = logging.getLogger(__name__)

# Retry configuration
COORDINATOR_MAX_RETRIES = 3
COORDINATOR_RETRY_BASE_SECONDS = 2


async def run_lens(client: LLMClient, lens_name: str, scene: str, indexes: dict[str, str],
                   model: str = MODEL, max_tokens: int = MAX_TOKENS) -> LensResult:
    """Run a single lens analysis."""
    prompt = get_lens_prompt(lens_name, scene, indexes)

    try:
        response = await client.create_message(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )

        return LensResult(
            lens_name=lens_name,
            findings=[],
            raw_output=response.text,
        )
    except Exception as e:
        return LensResult(
            lens_name=lens_name,
            findings=[],
            raw_output="",
            error=str(e),
        )


def _extract_tool_use_input(response) -> dict:
    """Extract the tool_use input dict from an LLMToolResponse.

    Raises CoordinatorError if the tool input is empty (no tool_use block found).
    """
    from .llm import LLMToolResponse

    if isinstance(response, LLMToolResponse):
        if response.tool_input:
            return response.tool_input
        raise CoordinatorError(
            "Coordinator response contained no report_findings tool call.",
            raw_output=response.raw_text,
        )

    # Fallback for unexpected response types
    raise CoordinatorError(
        f"Unexpected response type: {type(response).__name__}",
    )


def _validate_coordinator_output(data: dict) -> dict:
    """Validate and normalise the coordinator output.

    Ensures required top-level keys exist and each finding has required fields.
    Fills in sensible defaults for optional fields.
    Returns the (possibly patched) data dict.

    Raises CoordinatorError on structural problems that cannot be fixed.
    """
    REQUIRED_TOP = ("glossary_issues", "summary", "findings")
    for key in REQUIRED_TOP:
        if key not in data:
            raise CoordinatorError(
                f"Coordinator output missing required key '{key}'.",
                raw_output=json.dumps(data, indent=2)[:2000],
            )

    if not isinstance(data["findings"], list):
        raise CoordinatorError(
            "Coordinator 'findings' is not a list.",
            raw_output=json.dumps(data, indent=2)[:2000],
        )

    # Ensure optional top-level keys
    data.setdefault("conflicts", [])
    data.setdefault("ambiguities", [])

    VALID_SEVERITIES = {"critical", "major", "minor"}
    FINDING_REQUIRED = ("number", "severity", "lens", "location", "evidence", "impact", "options")

    for i, finding in enumerate(data["findings"]):
        for field in FINDING_REQUIRED:
            if field not in finding:
                raise CoordinatorError(
                    f"Finding #{i + 1} missing required field '{field}'.",
                    raw_output=json.dumps(finding, indent=2)[:1000],
                )
        # Normalise severity
        sev = finding["severity"].lower().strip()
        if sev not in VALID_SEVERITIES:
            logger.warning("Finding #%d has unrecognised severity '%s'; defaulting to 'major'.", i + 1, sev)
            sev = "major"
        finding["severity"] = sev

        # Defaults for optional finding fields
        finding.setdefault("flagged_by", [finding.get("lens", "unknown")])
        finding.setdefault("ambiguity_type", None)
        finding.setdefault("line_start", None)
        finding.setdefault("line_end", None)

        # Validate line_start/line_end when present
        ls = finding["line_start"]
        le = finding["line_end"]
        if ls is not None and not isinstance(ls, int):
            logger.warning("Finding #%d has non-integer line_start; clearing.", i + 1)
            finding["line_start"] = None
        if le is not None and not isinstance(le, int):
            logger.warning("Finding #%d has non-integer line_end; clearing.", i + 1)
            finding["line_end"] = None
        if (finding["line_start"] is not None and finding["line_end"] is not None
                and finding["line_start"] > finding["line_end"]):
            logger.warning("Finding #%d has line_start > line_end; swapping.", i + 1)
            finding["line_start"], finding["line_end"] = finding["line_end"], finding["line_start"]

    return data


def _dedup_findings_across_groups(findings: list[dict]) -> list[dict]:
    """Remove cross-group duplicates by comparing line ranges.

    Two findings are considered duplicates if their line ranges overlap
    significantly (>50% overlap).  When duplicates are found, keep the one
    with higher severity; merge ``flagged_by`` lists.
    """
    SEVERITY_RANK = {"critical": 3, "major": 2, "minor": 1}

    def _overlap(a: dict, b: dict) -> bool:
        a_start = a.get("line_start")
        a_end = a.get("line_end") or a_start
        b_start = b.get("line_start")
        b_end = b.get("line_end") or b_start
        if a_start is None or b_start is None:
            return False
        overlap_start = max(a_start, b_start)
        overlap_end = min(a_end, b_end)
        if overlap_start > overlap_end:
            return False
        overlap_len = overlap_end - overlap_start + 1
        min_len = min(a_end - a_start + 1, b_end - b_start + 1)
        return min_len > 0 and overlap_len / min_len > 0.5

    result = []
    for finding in findings:
        merged = False
        for existing in result:
            if _overlap(finding, existing):
                # Merge: keep higher severity, union flagged_by
                if SEVERITY_RANK.get(finding["severity"], 0) > SEVERITY_RANK.get(existing["severity"], 0):
                    existing["severity"] = finding["severity"]
                    existing["evidence"] = finding["evidence"]
                    existing["impact"] = finding["impact"]
                    existing["options"] = finding["options"]
                fb = set(existing.get("flagged_by", []))
                fb.update(finding.get("flagged_by", []))
                existing["flagged_by"] = sorted(fb)
                merged = True
                break
        if not merged:
            result.append(finding)
    return result


async def _run_coordinator_chunk(client: LLMClient, group_name: str,
                                 group_results: list[LensResult], scene: str, *,
                                 model: str = MODEL,
                                 max_tokens: int = COORDINATOR_MAX_TOKENS) -> dict:
    """Run a single coordinator chunk for one lens group.

    Returns validated coordinator output dict.
    Raises CoordinatorError on failure.
    """
    prompt = get_coordinator_chunk_prompt(group_name, group_results, scene)

    response = await client.create_message_with_tool(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        tool_schema=COORDINATOR_TOOL,
        tool_name="report_findings",
    )

    # Detect truncation
    if response.truncated:
        logger.warning(
            "Coordinator chunk '%s' was truncated at %d tokens.",
            group_name, max_tokens,
        )
        raise CoordinatorError(
            f"Coordinator chunk '{group_name}' output truncated at {max_tokens} tokens.",
        )

    data = _extract_tool_use_input(response)
    data = _validate_coordinator_output(data)
    return data


async def run_coordinator_chunked(client: LLMClient, lens_results: list[LensResult],
                                  scene: str, *, model: str = MODEL,
                                  max_tokens: int = COORDINATOR_MAX_TOKENS,
                                  progress_callback=None,
                                  lens_preferences: dict | None = None) -> dict:
    """Run the coordinator in 3 chunks (prose → structure → coherence).

    Each chunk is a smaller coordinator call that handles one lens group.
    Results are merged client-side: findings are concatenated, renumbered,
    and cross-group duplicates are removed.

    Falls back to a single ``run_coordinator()`` call if all chunks fail.
    """
    # Group lens results by lens group
    results_by_lens = {r.lens_name: r for r in lens_results}

    group_order = ["prose", "structure", "coherence"]
    all_findings = []
    all_glossary_issues = []
    all_conflicts = []
    all_ambiguities = []
    summary = {}

    for group_name in group_order:
        group_cfg = LENS_GROUPS[group_name]
        group_results = [
            results_by_lens[lens]
            for lens in group_cfg["lenses"]
            if lens in results_by_lens and not results_by_lens[lens].error
        ]

        if not group_results:
            logger.info("Skipping coordinator chunk '%s' — no successful lens results.", group_name)
            if progress_callback:
                progress_callback("status", {"message": f"Skipping {group_name} (no results)"})
            continue

        if progress_callback:
            progress_callback("status", {"message": f"Coordinating {group_name} findings..."})

        try:
            chunk = await _run_coordinator_chunk(
                client, group_name, group_results, scene,
                model=model, max_tokens=max_tokens,
            )

            all_findings.extend(chunk.get("findings", []))
            all_glossary_issues.extend(chunk.get("glossary_issues", []))
            all_conflicts.extend(chunk.get("conflicts", []))
            all_ambiguities.extend(chunk.get("ambiguities", []))
            if "summary" in chunk:
                summary.update(chunk["summary"])

            logger.info(
                "Coordinator chunk '%s': %d findings.",
                group_name, len(chunk.get("findings", [])),
            )

        except (CoordinatorError, Exception) as e:
            logger.warning("Coordinator chunk '%s' failed: %s", group_name, e)
            if progress_callback:
                progress_callback("warning", {
                    "message": f"Coordinator chunk '{group_name}' failed: {e}"
                })
            # Continue with other chunks — partial results are better than none

    if not all_findings:
        raise CoordinatorError("All coordinator chunks failed — no findings produced.")

    # Dedup across groups
    deduped = _dedup_findings_across_groups(all_findings)

    # Renumber sequentially
    for i, finding in enumerate(deduped, 1):
        finding["number"] = i

    # Ensure summary has all groups
    for group in ["prose", "structure", "coherence"]:
        summary.setdefault(group, {"critical": 0, "major": 0, "minor": 0})

    coordinated = {
        "findings": deduped,
        "glossary_issues": all_glossary_issues,
        "conflicts": all_conflicts,
        "ambiguities": all_ambiguities,
        "summary": summary,
    }
    if lens_preferences is not None:
        coordinated = rerank_coordinated_findings(coordinated, normalize_lens_preferences(lens_preferences))
    return coordinated


async def run_coordinator(client: LLMClient, lens_results: list[LensResult], scene: str, *,
                          model: str = MODEL, max_tokens: int = COORDINATOR_MAX_TOKENS,
                          max_retries: int = COORDINATOR_MAX_RETRIES,
                          lens_preferences: dict | None = None) -> dict:
    """Run the coordinator to merge and prioritize findings (single-call mode).

    Uses tool/function calling to guarantee structured JSON output, with automatic
    retry on transient failures.  Uses COORDINATOR_MAX_TOKENS for output budget.

    Raises CoordinatorError if all retries are exhausted.
    """
    prompt = get_coordinator_prompt(lens_results, scene)
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            response = await client.create_message_with_tool(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                tool_schema=COORDINATOR_TOOL,
                tool_name="report_findings",
            )

            # Detect truncation
            if response.truncated:
                raise CoordinatorError(
                    f"Coordinator output truncated at {max_tokens} tokens. "
                    "The scene may have too many findings for a single call.",
                )

            data = _extract_tool_use_input(response)
            data = _validate_coordinator_output(data)
            if lens_preferences is not None:
                data = rerank_coordinated_findings(data, normalize_lens_preferences(lens_preferences))
            return data

        except CoordinatorError:
            raise  # Structural issues won't be fixed by retrying

        except Exception as e:
            last_error = e
            logger.warning(
                "Coordinator attempt %d/%d failed: %s", attempt, max_retries, e
            )
            if attempt < max_retries:
                wait = COORDINATOR_RETRY_BASE_SECONDS ** attempt
                logger.info("Retrying in %ds...", wait)
                await asyncio.sleep(wait)

    raise CoordinatorError(
        f"Coordinator failed after {max_retries} attempts: {last_error}",
        attempts=max_retries,
    )


async def run_analysis(client: LLMClient, scene: str, indexes: dict[str, str],
                       model: str = MODEL, max_tokens: int = MAX_TOKENS,
                       lens_preferences: dict | None = None) -> dict:
    """Run all lenses in parallel and coordinate results.

    Uses the chunked coordinator by default (3 smaller calls by lens group).
    Falls back to the single-call coordinator if chunked fails.

    Raises CoordinatorError if coordination fails after all attempts.
    """

    print("Running 6 lenses in parallel...")

    lens_tasks = [
        run_lens(client, "prose", scene, indexes, model=model, max_tokens=max_tokens),
        run_lens(client, "structure", scene, indexes, model=model, max_tokens=max_tokens),
        run_lens(client, "logic", scene, indexes, model=model, max_tokens=max_tokens),
        run_lens(client, "clarity", scene, indexes, model=model, max_tokens=max_tokens),
        run_lens(client, "continuity", scene, indexes, model=model, max_tokens=max_tokens),
        run_lens(client, "dialogue", scene, indexes, model=model, max_tokens=max_tokens),
    ]

    lens_results = await asyncio.gather(*lens_tasks)

    for result in lens_results:
        if result.error:
            print(f"  Warning: {result.lens_name} lens failed: {result.error}")
        else:
            print(f"  ✓ {result.lens_name} lens complete")

    print("Coordinating results (chunked: prose → structure → coherence)...")
    try:
        coordinated = await run_coordinator_chunked(
            client, lens_results, scene, model=model,
            lens_preferences=lens_preferences,
        )
    except CoordinatorError:
        print("  Chunked coordinator failed. Falling back to single-call coordinator...")
        coordinated = await run_coordinator(
            client, lens_results, scene, model=model,
            lens_preferences=lens_preferences,
        )

    return coordinated


async def re_evaluate_finding(client: LLMClient, finding: Finding, scene_content: str,
                              model: str = MODEL, max_tokens: int = MAX_TOKENS) -> dict:
    """Re-evaluate a single stale finding against updated scene text.

    Sends the finding and new scene to the LLM for a focused check.

    Returns a dict with:
        status   – ``"updated"`` or ``"withdrawn"``
        For "updated": line_start, line_end, location, evidence, severity
        For "withdrawn": reason
    """
    prompt = get_re_evaluation_prompt(finding, scene_content)

    try:
        response = await client.create_message(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3].rstrip()

        result = json.loads(raw)

        outcome = apply_re_evaluation_result(finding, result)
        if outcome.get("status") == "error":
            logger.warning("Re-evaluation returned unexpected status: %s", result.get("status"))
        return outcome

    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Re-evaluation failed for finding #%d: %s", finding.number, e)
        return {"status": "error", "finding_number": finding.number, "error": str(e)}
