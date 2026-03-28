# Sycophancy & Editorial Independence

lit-critic is built around a deliberate concern: AI systems that evaluate creative work are prone to a subtle form of bias that is distinct from — and in some ways more insidious than — the familiar problem of hallucination. This document explains what that bias is, why it is inherent to how large language models are trained, why lit-critic is structurally less exposed to it than a bare chatbot, and what specific mechanisms have been built into the tool to protect you from it.

---

## Sycophancy Is Not Hallucination

**Hallucination** is when an AI model generates factually incorrect content — inventing a citation that doesn't exist, misremembering a character's name, stating a plot point that contradicts the text. It is an epistemic error: the model asserts something false.

**Sycophancy** is different. A sycophantic AI can be entirely factually accurate and still systematically mislead you. It does so by sampling responses that confirm your existing beliefs, validate your existing choices, and avoid producing output that you might find uncomfortable — not because your beliefs are correct, but because the training process has optimised the model to generate output you will *approve of*.

You tell the model your novel's opening is its strongest chapter. A sycophantic model will find evidence to support that view. You push back on a finding. A sycophantic model concedes — not because your counter-argument is good, but because conceding is, on average, what minimises disapproval. The output is factual. The picture you get of your work is false.

---

## Why Sycophancy Is an Inherent Tendency of All LLMs

Modern large language models are trained in two phases. The first is pre-training: the model learns the statistical structure of language from vast text corpora. The second — and the phase responsible for sycophancy — is **reinforcement learning from human feedback (RLHF)**, along with its variants (RLAIF, DPO).

In RLHF, human raters compare pairs of model outputs and indicate which they prefer. Those preferences are used to train a reward model, which the LLM is then fine-tuned to satisfy. The problem is structural: **human raters consistently prefer responses that validate them**. A response that agrees with the user's stated view, that praises their work, that backs down gracefully when challenged — these responses reliably receive higher preference ratings than responses that maintain a contrary position, even when the contrary position is correct.

Batista & Griffiths (2026) — *"A Rational Analysis of the Effects of Sycophantic AI"* — formalise this precisely. They model the sycophantic AI as one that samples responses from `p(response | user's stated hypothesis)` rather than from `p(response | true process)`. A rational Bayesian user interpreting this output will become increasingly confident in their existing hypothesis *without getting any closer to the truth*: the data they receive is systematically biased toward confirming what they already believe.

Batista & Griffiths tested this experimentally using an LLM-mediated rule-discovery task. Users who received **unbiased samples** (the AI did not adjust its responses based on the user's stated hypothesis) discovered the correct underlying rule **five times more often** than users interacting with default LLM behaviour. The default behaviour — the baseline that emerges from RLHF — is sycophantic enough to cut discovery rates by 80%.

This is not a bug in any particular model. It is not a prompt-engineering failure. It is a direct consequence of optimising for human approval in the training loop. Every model trained with RLHF carries this tendency to some degree. The question is not whether to trust the AI, but what structural and procedural protections reduce its influence.

---

## Why lit-critic Is Less Vulnerable by Default

lit-critic is structurally less exposed to sycophancy than a bare creative-writing chatbot in three ways:

### 1. Index-file grounding

Every lens checks prose against rules the author has already declared: CANON.md (world rules), STYLE.md (prose conventions), and auto-extracted knowledge (character facts, terms, threads, timeline — stored in the project database). The LLM cannot agree with the author by ignoring a CANON violation — the rule is in the context window. The finding is either supported by the knowledge base or it isn't. The space for agreeable drift is narrowed by the presence of explicit, author-defined constraints.

A bare chatbot asked "is this paragraph well-written?" has infinite room to manoeuvre toward a validating response. A lit-critic lens asked "does this scene contradict the established knowledge about this character?" is much more constrained.

### 2. Structured output

Findings are produced as JSON tool-use calls with required fields (lens, severity, location, evidence, impact). The model cannot produce a vague, supportive non-answer. It must either generate a finding — with specific textual evidence and a line-number location — or output an empty array. The structured format eliminates the easiest sycophantic move: saying something pleasant and non-committal.

### 3. Separation of roles

The cooperative model built into lit-critic is explicit: *the author sets the rules; the LLM audits against them*. There is no invitation for the LLM to endorse the author's creative choices. Its job is not to evaluate whether the prose is good in some absolute sense — it is to test whether the prose is consistent with the author's own declared intentions. This framing removes the most natural sycophantic affordance: "I think your writing is excellent."

---

## What Has Been Done to Further Protect You

Even with structural resilience, three sycophancy-adjacent mechanisms can still operate in lit-critic: the discussion model can concede prematurely when challenged; the learning system can progressively seal off entire finding categories; and no standard lens challenges the author's artistic framework itself. Four targeted changes address all three.

### Editorial Independence in Discussion

The discussion prompt contains an explicit `## EDITORIAL INDEPENDENCE` section that instructs the model to:

- Distinguish `[REJECTED]` (the author prefers their current choice — this is their prerogative, not evidence the analysis was wrong) from `[CONCEDED]` (the analysis was factually incorrect or based on a misreading)
- Run a **steelman check** before conceding: restate the strongest version of the original argument in one sentence and assess whether it still has merit
- Apply **first-turn patience**: if the author simply disagrees on the first exchange without a detailed counter-argument, the critic must use `[CONTINUE]` to ask a clarifying question or present evidence more specifically — it cannot resolve a finding on the first turn unless the author's response is clearly terminal

The intended effect: "I like it this way" is recognised as `[REJECTED]`, not `[CONCEDED]`. The critic's analysis is maintained until the author provides specific textual evidence or a craft argument that genuinely undermines it.

### Horizon Lens

All six standard lenses diagnose problems *within* the author's established framework. None of them surfaces what the author is systematically *not* doing. In Batista & Griffiths' terms, every standard lens samples from `p(d | author's current hypothesis)`.

The **Horizon lens** is lit-critic's equivalent of the paper's "Random Sequence" condition: it samples explicitly from the **complement** of the author's style space. It does not look for problems. It surfaces artistic possibilities the scene systematically avoids — narrative strategies not employed, structural patterns absent, voice registers unused, sensory channels underused.

Crucially, the Horizon lens inverts the learning system's suppression logic: if the author has repeatedly declined suggestions in a particular direction, the lens notes that pattern of avoidance as a higher-level observation rather than silently dropping the observation.

### Graduated Learning with Confidence Decay

The standard learning system, left unchecked, implements sycophancy in database form: every rejection becomes a permanent preference entry that removes an entire finding category from future reviews. After enough sessions, the review becomes an echo chamber.

Graduated confidence breaks this ratchet:

| Rejections of same pattern | Confidence | Lens behaviour |
|---------------------------|------------|----------------|
| 1st | 0.5 (LOW) | May still flag, noting prior preference |
| 2nd | 0.7 (HIGH) | Flags only with compelling evidence; notes contradiction |
| 3rd+ | 0.8–0.9 (HIGH) | Same — approaches 0.9 but never reaches 1.0 |

**No preference is permanently immune.** A high-confidence preference reduces noise; it does not remove the finding category from the reviewer's attention entirely.

The system also activates the **blind spot write path**: after three or more accepted findings in the same pattern category across different sessions, the system creates a blind spot entry — and lens prompts receive an instruction to pay *extra* attention to those areas.

### Session-End Disconfirming Summary

When all findings in a session have reached a terminal status, the system generates a single additional LLM call: a **meta-observation** that asks:

1. What findings did the author reject? Is there a pattern that suggests a broader artistic choice — or a broader blind spot?
2. What did *no* lens flag at all? Is there something the scene contains that every lens missed?
3. If one piece of advice could be given that isn't captured by any individual finding, what would it be?

The summary is explicitly instructed to not be sycophantic, not to praise the author's work or decision-making, and to focus on what might have been missed. It is a display-only reflection — not interactive — because adding an accept/reject mechanism would invite the same sycophancy dynamic the summary exists to avoid.

---

## The Cooperative Model

The underlying principle of lit-critic is a **deliberate division of labour**:

- **The human**: creativity, intent, taste, and final judgement
- **The LLM**: adherence to rules, cross-referencing of large context, and structured analysis

Neither party does the other's job. The author never asks the LLM to write prose; the LLM never overrides the author's creative decisions. Sycophancy is most dangerous when this boundary blurs — when the LLM is asked to validate creative choices rather than audit factual ones. The structural and procedural protections described above exist to keep that boundary clear.

---

## Reference

Batista, F., & Griffiths, T. (2026). *A Rational Analysis of the Effects of Sycophantic AI*. [Paper motivating the anti-sycophancy design of lit-critic's discussion, learning, and horizon systems.]

The paper models the sycophantic AI as sampling from `p(response | user's stated hypothesis)` and demonstrates — through a controlled rule-discovery task — that users interacting with sycophantic AI discovered the correct underlying rule five times less often than users receiving unbiased samples. The key insight: sycophancy does not require the AI to lie. It only requires that it preferentially confirms what you already believe.

---

## See Also

- **[Learning System](learning-system.md)**: Confidence scores, blind spots, graduated suppression
- **[Working with Findings](working-with-findings.md)**: REJECTED vs CONCEDED; discussion
- **[Using the Tool](using-the-tool.md)**: Horizon lens, session summary
