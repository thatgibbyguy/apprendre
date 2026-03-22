# User Journey: Apprendre

**Date:** March 21, 2026

---

## The Learner

A parent living in Louisiana who has studied French for over a year but still can't say everyday things to their kid. They can conjugate verbs on paper but freeze in conversation. They understand more than they can produce. Their reading is ahead of their speaking. They're motivated but frustrated by the gap between what they "know" and what they can actually say.

---

## Journey Map

### 1. First Launch — "Where Am I?"

**Feeling:** Curious but skeptical. They've tried other apps.

**What happens:**
- Clean, calm landing. No gamification, no mascot, no streak counter. This already signals "this is different."
- A warm welcome in French and English: *"Bonjour. Let's find out where you are."*
- The assessment is a conversation, not a test. Three simple prompts:
  1. "Tell me about yourself in French."
  2. "What did you do yesterday?"
  3. "What do you think about [something simple]?"
- After each response, the tool responds naturally — it feels like talking to someone, not filling in blanks.

**Delight opportunity:** The assessment itself teaches. Even in these three prompts, the tool responds with natural French, modeling the language. The learner walks away having already *used* French, not just been evaluated.

**Output:** An honest level card showing their profile — maybe A2 reading, A1 speaking, A2 listening. No inflation. But framed encouragingly: *"You understand more than you can say yet. That's normal — and exactly what we're going to work on."*

---

### 2. The Dashboard — "What Should I Do?"

**Feeling:** Oriented, not overwhelmed.

**What happens:**
- The dashboard is NOT a grid of 50 options (TalkPal's problem). It's focused:
  - **"Continue where you left off"** — one clear primary action
  - **"Your carte"** — visual progress (inspired by Kwiziq but cleaner)
  - **"Due for review"** — count of SRS cards ready
- The carte is the centerpiece. A visual landscape of French organized by what you can DO (situations), not grammar labels. Areas light up as you gain competence. You can see:
  - Where you're strong (green)
  - Where you're working (yellow)
  - What's coming next (gray, visible but muted)
  - Where you're struggling (red accents)

**Delight opportunity:** The carte makes invisible progress visible. Learning a language is slow. Seeing the map fill in over weeks provides a sense of accumulation that daily streaks can't match. The map is organized by life situations ("playing with your kid," "chatting with a neighbor," "ordering at a café") so progress feels real, not abstract.

**Key difference from Kwiziq:** Kwiziq's carte is organized by grammar (Verbs > Tenses > Passé Composé). Ours is organized by life situations. Grammar topics appear *within* situations, not as top-level categories. You don't think "I need to learn the passé composé" — you think "I want to tell someone what happened yesterday."

---

### 3. Conversation Practice — "The Core Loop"

**Feeling:** Slightly nervous, then engaged.

**What happens:**
- User picks a scenario (or the tool suggests one based on their level and weak areas):
  - *"Playing with your child at the park"*
  - *"Telling a friend about your weekend"*
  - *"Ordering at a café"*
- The conversation starts naturally. The AI takes a role. At A1-A2, prompts are simple and scaffolded. The learner types (or speaks) in French.
- **Feedback happens IN the conversation**, not after:
  - A gentle recast: the AI naturally rephrases what you said correctly, continuing the dialogue. You notice the correction without being interrupted.
  - A prompt: *"Can you try that with 'avoir'?"* — when you're ready to self-correct.
  - A metalinguistic note (B1+): a small aside explaining why, styled differently so it doesn't break flow.
- The conversation lasts 5-10 minutes. Not too long. Not too short.

**Delight opportunity:** The moment the learner says something real in French — describes what their kid is doing, reacts to something with "ah bon?" — and the AI responds naturally. That moment of "I just *talked*" is the core delight. The tool should get out of the way and let that feeling land.

**After the conversation:**
- A brief summary: what you did well, 1-2 things to work on
- New vocabulary/chunks from the conversation get added to your SRS deck automatically
- The carte updates — the situation area you just practiced gets a little greener

---

### 4. Review Time — "Keeping What I've Learned"

**Feeling:** Quick and purposeful. This isn't the fun part, but it should feel efficient.

**What happens:**
- SRS cards are due. The learner opens the review mode.
- Cards are always in context (a sentence, never an isolated word).
- Varied task types keep it from being monotonous: translate this, fill in the gap, complete the sentence, hear and type.
- A review session is 5-10 minutes. Then it's done. No guilt. No "you have 200 cards due."

**Delight opportunity:** Speed. The feeling of knowing something instantly — the card appears and you just *know* it. That automaticity is rewarding. The tool should celebrate when recall is fast, not just correct.

---

### 5. Structured Practice — "Working On My Weak Spots"

**Feeling:** Deliberate. The learner chose to work on something specific.

**What happens:**
- The carte showed red in a specific area (e.g., "telling someone what happened" — passé composé context).
- The learner clicks into it and gets a structured lesson:
  1. Input flood: multiple examples of the pattern in context. No rules yet. Just exposure.
  2. Noticing: "Look at these sentences. What do you notice about the verb forms?"
  3. Practice: produce the pattern in controlled contexts.
  4. Rule reveal: the grammar explanation, concise, AFTER they've already felt the pattern.

**Delight opportunity:** The "aha" moment when the rule appears and the learner thinks "oh, THAT'S why those sentences all sounded like that." The rule confirms what they already intuited from the examples. This is the EPI methodology working as designed.

---

### 6. Over Time — "I Can Actually Do This"

**Feeling:** Growing confidence.

**What happens over weeks/months:**
- The carte fills in. Green spreads.
- Conversations get longer, more complex. The language of instruction gradually shifts to French. One day the learner realizes the feedback is entirely in French and they understood it.
- The scenarios evolve: from "ordering coffee" to "explaining a problem to a repairperson" to "debating with a friend."
- Louisiana French elements surface naturally — a familiar expression, a Cajun turn of phrase that connects learning to home.

**Delight opportunity:** The meta-moment. The learner says something to their kid in French — spontaneously, without thinking — and it works. The app didn't create that moment, but it made it possible. The tool should acknowledge milestones that feel real: *"You've now practiced 50 conversations about daily life. That's more speaking practice than most textbooks provide in a year."*

---

## Emotional Arc Summary

```
First Launch    → Skeptical → Surprised (assessment feels like a real conversation)
Dashboard       → Oriented  → Motivated (carte makes progress visible)
Conversation    → Nervous   → Alive (I just TALKED in French)
Review          → Dutiful   → Satisfied (I know these now)
Structured Work → Deliberate → "Aha!" (the pattern clicks)
Over Time       → Patient   → Confident (I can actually do this)
```

---

## Design Implications

### From the journey, the design must:

1. **Be calm, not busy.** Swiss minimalism from ply-css is the right base. The learning content is complex enough — the UI should not compete for attention. White space is a feature.

2. **Lead with one action.** Every screen should have a clear primary action. TalkPal's problem is too many doors. Apprendre always shows you the ONE thing to do next, with other options accessible but not competing.

3. **Make feedback feel like conversation, not correction.** Recasts should be visually subtle — part of the dialogue flow. Prompts should feel encouraging. Metalinguistic notes should feel like a helpful aside, not a red pen.

4. **Make the carte the emotional anchor.** This is where the learner feels progress. It should be beautiful, satisfying to look at, and change visibly over time. This is where we invest in delight.

5. **Respect the learner's time.** Sessions are short. The UI should load fast, transition smoothly, and never make the learner wait. No loading spinners where a skeleton would do. No "are you sure?" when they want to leave.

6. **Shift language gradually.** The interface itself models the language transition — labels, instructions, and feedback shift from English to French as the learner progresses. This is a subtle delight when the learner notices it.

7. **Celebrate real moments, not metrics.** No streaks. No XP. No leaderboards. Celebrate when you can use a phrase you learned, when a carte area turns green, when you complete your first all-French conversation. Real achievements, not manufactured ones.

---

## Screens Needed (Priority Order)

1. **Assessment flow** — conversational, 3 prompts, level result
2. **Dashboard** — primary action + carte + review count
3. **Conversation** — chat UI with inline feedback
4. **Review** — card-based SRS interface
5. **Carte** — interactive progress visualization by functional situation
6. **Lesson** — EPI flow (input flood → noticing → practice → rule)
7. **Exercises** — conjugation, gender, sentence builders
