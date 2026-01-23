# Onboarding Quiz Audit

**Date:** 2026-01-23  
**Issue:** Synthesized guidance was generic despite 15 rich user answers

## Root Cause Found

**BUG:** `interview_answers` were stored in session but NOT copied to final `onboarding_data` payload.

- Session had 15 detailed answers
- Final payload had 0 answers  
- Synthesis LLM had nothing to work with → copied example output

**Fix:** Added `interview_answers` to `OnboardingPayload.to_dict()` and `build_payload_from_state()`.

---

## Your Actual Answers (from session)

```
1. Q: When you're following a recipe—say for a Thai curry or Italian...
   A: I like clear steps always. I like temperatures and times and cues to look out for...

2. Q: When cooking chicken thighs or veggies, do you rely on exact...
   A: 100% temperatures. Time not so much but more guidance. Temperature + poke/cut test...

3. Q: How much in-the-moment help do you want from a recipe?
   A: I need as much help as possible. Especially the why. Don't substitute unless I ask...

4. Q: On a typical weeknight, how much time do you like to spend...
   A: On a weeknight I can spare 20-30 min total cook + assembly + cleanup. I love using...

5. Q: How do you usually plan your cooking week?
   A: I like to cook a few meals in the weekend 2 or 3 and reheat them. Often I cook components...

6. Q: What's your approach to leftovers?
   A: I like leftovers maybe once tops but I am okay to reuse component ingredients in new dishes...

7. Q: How much do you use your freezer for meal prep?
   A: I prefer to freeze only sauces that freeze well. I don't like freezing cooked proteins...

8. Q: When it comes to prep reminders...
   A: Links to meals are always helpful. Timing would be needed. Treat me like a beginner...

... (15 answers total)
```

---

## Quiz Distribution Analysis

| Page | Focus | Questions | Maps To |
|------|-------|-----------|---------|
| 1 | Cooking Style | 4 | recipes |
| 2 | Planning & Prep | 4 | meal_plans, tasks |
| 3 | Exploration & Goals | 4 | recipes, meal_plans, shopping, inventory |
| 4 | Catch-all | 0-4 | fill gaps |

**Current distribution is reasonable** - recipes and meal_plans get most coverage.

---

## Synthesis Prompt Issue

The synthesis prompt (`SYNTHESIZE_GUIDANCE_PROMPT`) includes a detailed example output. When synthesis received NO answers (due to bug), the LLM just copied the example.

### Example in Prompt vs Your Stored Guidance

```
Prompt Example:
"recipes": "Always provide clear, step-by-step instructions with precise temperatures..."

Your Stored Guidance (generic):
"recipes": "Always provide clear, step-by-step instructions with precise temperatures..."
```

**Nearly identical!** The LLM had no personalization signal.

---

## Action Items

1. ✅ **BUG FIX** - interview_answers now copied to payload
2. 🔄 **RE-RUN** - User needs to redo onboarding OR manually re-synthesize
3. ⏳ **OPTIONAL** - Reduce example influence in synthesis prompt (shorter example, or "Example ONLY - personalize heavily" warning)

---

## To Re-synthesize Your Answers

Option A: Re-do onboarding quiz (answers are still in session)

Option B: Manual API call to re-synthesize:
```bash
curl -X POST http://localhost:8000/api/onboarding/interview/synthesize \
  -H "Authorization: Bearer <token>"
```

This will use your 15 stored answers and should produce personalized guidance like:

```
"recipes": "Clear step-by-step with exact temperatures for proteins. 
Include visual cues AND temp targets. Explain the 'why' behind techniques. 
Never substitute unless asked. Air fryer/skillet focus on weeknights (20-30 min), 
more involved Instant Pot/oven dishes on weekends..."
```
