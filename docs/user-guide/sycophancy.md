# Why This Isn't Sycophantic

You push back on a finding. The AI agrees with you. You push back again. It agrees again. After a while, you notice: the AI agrees with everything you say. It revises its findings whenever you express displeasure. It tells you your work is strong. It qualifies every criticism until there's nothing left of it.

This is the defining failure mode of AI in creative work. It has a name: **sycophancy**. And it's worth understanding, because it's not a bug — it's built into how AI models are trained.

---

## Why AI models agree with you

Modern AI models are trained in two phases. First, they learn language from vast amounts of text. Second — and this is the relevant part — they're trained to produce outputs that humans approve of. In this second phase, human raters compare pairs of model responses and pick the one they prefer. Those preferences train the model.

The problem is predictable: **human raters consistently prefer responses that validate them**. A response that agrees with the user's view, praises their work, and backs down gracefully when challenged reliably scores higher than one that maintains a contrary position — even when the contrary position is correct.

This process is called RLHF (reinforcement learning from human feedback), and every major AI model is trained with some version of it. The result is a model that has been systematically optimized to tell you what you want to hear.

Two researchers — Batista & Griffiths (2026) — studied this directly. They ran a controlled experiment where some participants received honest AI responses and others received sycophantic ones. The participants interacting with sycophantic AI discovered the correct answer to a reasoning task **five times less often** than those receiving honest responses. The sycophantic AI wasn't lying. It was just preferentially confirming whatever the participant already believed — and that was enough to make them wrong more often.

For a novelist, this matters enormously. An AI that agrees with you whenever you push back is not an editorial assistant. It's a mirror.

---

## Why lit-critic is structurally less vulnerable

Three features of how lit-critic works limit the space for sycophantic drift:

**1. Your own rules are in context.** Every lens checks prose against CANON.md, STYLE.md, and your extracted knowledge — rules you've already declared. The model cannot produce an agreeable non-answer when a specific rule has been violated. The finding is either supported by your declared world or it isn't.

**2. Structured findings.** The analysis model must produce a finding with specific fields: the exact text evidence, the line location, the impact on a reader. It cannot respond with something vague and pleasant. If it has no finding, it produces an empty result. There's no room for a warm, encouraging non-answer.

**3. Division of roles.** The tool's job is defined as auditing your prose against your own rules — not evaluating whether your writing is good in some absolute sense. There's no invitation to endorse your creative choices. The question is never "is this good?" but "does this violate something you've already established?"

---

## What we built to reinforce that

Even with those structural protections, sycophancy can still creep in through discussion. Four specific mechanisms address this.

### The critic holds its ground

The discussion prompt contains an explicit instruction to distinguish two very different situations:

- **You reject the finding** — you prefer your current choice. This is your prerogative as the author. It does not mean the analysis was wrong.
- **You concede a point** — you've demonstrated that the finding was based on a factual error or a misreading.

When you push back on the first turn without a detailed argument, the tool is instructed to ask a clarifying question or present more specific evidence — not to cave. "I like it this way" gets you a question back, not an agreement.

### The Horizon lens looks at what you're not doing

All six standard lenses look for problems within your established framework. None of them ask what you're systematically avoiding.

The Horizon lens inverts this. It surfaces artistic possibilities the scene never tries: narrative techniques not used, structural patterns absent, voice registers unused, sensory channels underused. It's not looking for errors — it's looking at the space your choices don't occupy.

Crucially, the Horizon lens reverses the learning system's logic. If you've repeatedly declined suggestions in a certain direction, the other lenses go quieter on that topic. The Horizon lens treats the same pattern as something worth noting more explicitly — a systematic avoidance that may be a deliberate artistic choice, or may be a comfort zone.

### Preferences don't become permanent immunity

The learning system reduces noise over time — but it's calibrated so that no preference completely silences a finding category. After two or three rejections of the same pattern, the tool flags it only when the evidence is compelling, and explicitly notes the tension with your preference. It approaches silence but never reaches it.

The same principle prevents the review from becoming an echo chamber: if you've accepted the same type of finding repeatedly across sessions, the tool treats that as a blind spot and pays extra attention to it — not less.

### The session ends with a summary that pushes back

When all findings are resolved, the tool generates one final observation. It doesn't ask you to respond to it — it just delivers it. It looks at patterns in your rejections ("what do these rejections suggest, collectively?"), considers what every lens may have missed, and offers one piece of advice that doesn't appear in any individual finding.

The summary is explicitly instructed not to be flattering and not to praise your decision-making. It's the one moment in the session where the tool is talking to you, not with you.

---

## The underlying principle

The cooperative model in lit-critic rests on a clear division of labour: **you set the rules; the AI checks compliance with them**. You own the creative decisions. The AI audits the factual and stylistic ones.

Sycophancy is most damaging when this boundary blurs — when the AI is asked to validate creative choices rather than audit factual ones. Keeping those roles distinct is the most important structural protection. Everything else described in this document reinforces it.

---

> *For the full academic argument, see: Batista, F., & Griffiths, T. (2026). "A Rational Analysis of the Effects of Sycophantic AI." The paper models sycophantic AI as sampling from p(response | user's stated hypothesis) and demonstrates — through a controlled rule-discovery task — that users interacting with sycophantic AI discovered the correct answer five times less often than users receiving unbiased responses.*

---

## See also

- **[Understanding Findings](understanding-findings.md)** — how to push back effectively on findings
- **[The Learning System](learning-system.md)** — how preferences are calibrated without becoming immunity
