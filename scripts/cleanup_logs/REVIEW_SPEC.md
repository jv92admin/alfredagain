# Dedupe Review Enrichment — Task Spec

## Goal

Read the merge groups in `dedupe_dryrun_20260128.txt` and produce an enriched version (`dedupe_reviewed.txt`) where each merge line has three annotations appended so a human can quickly approve or reject it.

## Input

The file `dedupe_dryrun_20260128.txt`. The relevant section starts after the line `[DRY RUN] Would merge:`. Each merge group is a single line like:

```
  -> Keep 'apricot', merge: ['abe906e4-...', '12a743a5-...'] (singular/plural variant)
```

Ignore all lines before `[DRY RUN] Would merge:` — copy them to the output unchanged.

## Your Task

For each merge line, append three fields on new indented lines directly below it:

```
  -> Keep 'apricot', merge: ['abe906e4-...', '12a743a5-...'] (singular/plural variant)
     CONTEXT: "apricot" (singular) and "apricots" (plural). Same fruit, just pluralization.
     RISK: LOW — these are unambiguously the same ingredient.
     VERDICT: [APPROVE / SKIP / UNSURE]
```

### Field Definitions

**CONTEXT** — One sentence explaining what the items actually are, in plain English. Include the names of BOTH the canonical item AND the items being merged into it. Don't just repeat the reason — actually describe the ingredients.

Example (good): `"apricot" and "apricots" — same stone fruit, plural form.`
Example (good): `"garlic" (whole head) and "garlic clove" (peeled segment) — different prep states of the same ingredient but a recipe calling for "2 garlic" vs "2 garlic cloves" means different quantities.`
Example (bad): `singular/plural variant` ← this just repeats the reason, useless.

**RISK** — Rate the merge risk. Use one of:

| Rating | Meaning | Examples |
|--------|---------|---------|
| `LOW` | Unambiguously the same thing. Merging is safe. | carrot/carrots, lemon/lemons, agar agar/agar-agar |
| `MEDIUM` | Probably the same, but there's a meaningful form/prep difference that COULD matter in some recipes. | garlic/garlic clove, ginger root/ground ginger, cumin seeds/ground cumin |
| `HIGH` | These might be legitimately different ingredients that should stay separate. | apple/apple juice, yogurt/labneh, sea salt/smoked salt, sweetened condensed milk/sweetened condensed coconut milk |

**VERDICT** — Your recommendation:

| Verdict | When to use |
|---------|-------------|
| `APPROVE` | LOW risk. No-brainer merge. |
| `SKIP` | HIGH risk. These should stay separate. |
| `UNSURE` | MEDIUM risk. Human should decide. Flag for review. |

## Rules

1. **Be conservative.** When in doubt, mark UNSURE, not APPROVE.
2. **Different physical forms that affect recipes should be MEDIUM or HIGH:**
   - Whole spice vs ground spice → MEDIUM (recipes specify which)
   - Fresh herb vs dried herb → HIGH (different quantities, different flavor)
   - Raw ingredient vs processed product → HIGH (flour vs wheat, milk vs cheese)
3. **Regional name variants of the SAME thing are LOW:**
   - cilantro/coriander leaves → LOW
   - scallion/green onion/spring onion → LOW
   - eggplant/aubergine → LOW
4. **Sub-products of an ingredient are HIGH:**
   - coconut vs coconut milk → HIGH (completely different in recipes)
   - apple vs apple juice → HIGH
   - tomato vs tomato paste → HIGH
5. **Cuts of the same protein are MEDIUM:**
   - chicken breast/chicken breast cutlet → MEDIUM
   - beef short ribs/flanken → LOW (just different names for the same cut)
6. **Never merge line content** — keep the original `-> Keep ...` line exactly as-is. Only append the three annotation lines below it.

## Output Format

Write the enriched file to `dedupe_reviewed.txt` in the same directory. The format is:

```
[all header lines unchanged]

[DRY RUN] Would merge:
  -> Keep 'acai berry', merge: ['7b09844a-...', '8146957e-...'] (regional name/spelling variant)
     CONTEXT: "acai berry" and "acaí berries" — same superfruit, diacritic and plural difference.
     RISK: LOW
     VERDICT: APPROVE
  -> Keep 'garlic', merge: ['410fbfb8-...', '98b469f4-...'] (whole vs clove)
     CONTEXT: "garlic" (whole head) and "garlic clove" (individual segment). Recipes distinguish between these — "3 cloves garlic" vs "3 garlic" means very different amounts.
     RISK: HIGH
     VERDICT: SKIP
```

## Deliverable

A single file: `scripts/cleanup_logs/dedupe_reviewed.txt` with all ~293 merge lines annotated. The human reviewer will then:
1. Scan for SKIP/UNSURE lines
2. Override any VERDICT they disagree with
3. Hand the file back for migration generation
