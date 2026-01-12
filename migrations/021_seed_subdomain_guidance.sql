-- Migration 021: Seed Subdomain Guidance Examples
-- Example preference modules for test users

-- Alice (beginner, household of 1) - simple, learning-focused
UPDATE preferences 
SET subdomain_guidance = '{
    "inventory": "I track basics loosely. Assume common staples (oil, salt, basic spices) are always available even if not listed.",
    "recipes": "I am learning to cook. Include brief explanations for techniques. Keep recipes to 5-7 steps max. Metric measurements preferred.",
    "meal_plans": "I cook 2-3 times per week, usually on Sunday and Wednesday evenings. I like simple meals on weeknights. Leftovers are great for lunches.",
    "shopping": "I shop once a week at Trader Joes. I prefer to consolidate trips. Okay with reasonable substitutions.",
    "tasks": "Remind me about prep the day before. I tend to forget to thaw things."
}'::jsonb
WHERE user_id = '00000000-0000-0000-0000-000000000002';

-- Bob (intermediate, household of 2) - more adventurous
UPDATE preferences 
SET subdomain_guidance = '{
    "inventory": "We track fridge items carefully but pantry loosely. Check expiry dates when suggesting proteins.",
    "recipes": "We enjoy trying new cuisines. Medium-complexity recipes are fine. We have a well-stocked spice cabinet.",
    "meal_plans": "We batch cook on Sundays for the week. Weeknight meals should be 30 min max active time. We eat dinner together around 7pm.",
    "shopping": "We split shopping between Costco (bulk) and local grocery (fresh). We can plan around sales.",
    "tasks": "We prep sauces and marinades ahead. Link prep tasks to specific meals when possible."
}'::jsonb
WHERE user_id = '00000000-0000-0000-0000-000000000003';

-- Carol (advanced, household of 4) - family-focused, efficient
UPDATE preferences 
SET subdomain_guidance = '{
    "inventory": "Large family - we go through staples fast. Assume we have basics. Focus on proteins and fresh produce availability.",
    "recipes": "Skip obvious technique explanations. Scale recipes for 6 servings by default. Note which dishes reheat well for school lunches.",
    "meal_plans": "Cooking most nights. Need variety but also crowd-pleasers. Sunday is elaborate cooking day, weeknights need to be efficient.",
    "shopping": "Weekly Costco run plus midweek fresh produce. Budget-conscious but quality matters for proteins.",
    "tasks": "Plan prep around kids activities. Morning prep preferred over evening when possible."
}'::jsonb
WHERE user_id = '00000000-0000-0000-0000-000000000004';
