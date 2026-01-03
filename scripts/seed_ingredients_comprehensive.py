"""
Comprehensive Ingredient Seeding Script v2.

Uses GPT to generate 3000+ cooking ingredients organized by:
1. Base categories (produce, proteins, dairy, etc.) - high counts
2. Cuisine-specific ingredients (Korean, Indian, Mexican, etc.)

Run: python scripts/seed_ingredients_comprehensive.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

# Use alfred's db client
try:
    from alfred.db.client import get_client
except ImportError:
    from supabase import create_client
    def get_client():
        return create_client(
            os.environ.get("SUPABASE_URL"),
            os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
        )

# =============================================================================
# BASE CATEGORIES - Universal ingredients with high counts
# =============================================================================
BASE_CATEGORIES = [
    # Produce - Vegetables (subdivided for better coverage)
    ("vegetables_leafy", "Leafy greens and salad vegetables: lettuces, spinach, kale, chard, arugula, cabbage varieties, bok choy, etc.", 40),
    ("vegetables_root", "Root vegetables: potatoes (all varieties), carrots, beets, turnips, parsnips, radishes, sweet potatoes, yams, etc.", 35),
    ("vegetables_allium", "Allium family: onions (all types), garlic, shallots, leeks, scallions, chives, ramps, etc.", 25),
    ("vegetables_cruciferous", "Cruciferous vegetables: broccoli, cauliflower, brussels sprouts, kohlrabi, etc.", 20),
    ("vegetables_nightshade", "Nightshades: tomatoes (all varieties), peppers (bell, hot), eggplant varieties, etc.", 35),
    ("vegetables_squash", "Squash and gourds: zucchini, butternut, acorn, spaghetti squash, pumpkin, cucumber, etc.", 30),
    ("vegetables_other", "Other vegetables: asparagus, artichokes, corn, celery, fennel, mushrooms (all varieties), etc.", 50),
    
    # Produce - Fruits
    ("fruits_citrus", "Citrus fruits: oranges, lemons, limes, grapefruit, tangerines, yuzu, Meyer lemon, etc.", 25),
    ("fruits_berries", "Berries: strawberries, blueberries, raspberries, blackberries, cranberries, gooseberries, etc.", 25),
    ("fruits_stone", "Stone fruits: peaches, plums, cherries, apricots, nectarines, mangoes, etc.", 25),
    ("fruits_tropical", "Tropical fruits: bananas, pineapple, papaya, coconut, passion fruit, guava, dragon fruit, lychee, etc.", 35),
    ("fruits_pome", "Pome and other fruits: apples (varieties), pears, grapes, figs, dates, pomegranate, kiwi, etc.", 30),
    
    # Fresh Herbs (extensive)
    ("herbs_fresh", "Fresh culinary herbs: basil (varieties), cilantro, parsley, mint, dill, thyme, rosemary, oregano, tarragon, chervil, sage, marjoram, lemongrass, curry leaves, kaffir lime leaves, shiso, Thai basil, etc.", 50),
    
    # Proteins - Poultry
    ("poultry", "Poultry cuts and products: chicken (whole, breast, thigh, wing, drumstick, ground), turkey (cuts), duck, quail, Cornish hen, etc.", 40),
    
    # Proteins - Beef
    ("beef", "Beef cuts: ribeye, sirloin, tenderloin, brisket, chuck, short ribs, flank, skirt, ground beef varieties, oxtail, beef cheeks, etc.", 45),
    
    # Proteins - Pork
    ("pork", "Pork cuts and products: loin, chops, tenderloin, belly, shoulder, ribs, ground pork, bacon varieties, ham, pancetta, guanciale, etc.", 45),
    
    # Proteins - Lamb & Game
    ("lamb_game", "Lamb cuts and game meats: lamb chops, leg, shoulder, rack, ground lamb, venison, rabbit, bison, goat, etc.", 35),
    
    # Seafood - Fish
    ("fish", "Fish varieties: salmon (varieties), tuna, cod, halibut, sea bass, snapper, tilapia, trout, mackerel, sardines, anchovies, swordfish, mahi mahi, catfish, etc.", 50),
    
    # Seafood - Shellfish
    ("shellfish", "Shellfish and mollusks: shrimp (sizes), crab varieties, lobster, scallops, mussels, clams, oysters, squid, octopus, crawfish, etc.", 40),
    
    # Dairy - Milk & Cream
    ("dairy_milk", "Milk and cream products: whole milk, skim, 2%, heavy cream, half-and-half, buttermilk, condensed milk, evaporated milk, coconut cream, oat milk, almond milk, etc.", 30),
    
    # Dairy - Cheese (extensive)
    ("cheese_fresh", "Fresh and soft cheeses: mozzarella, burrata, ricotta, cottage cheese, cream cheese, mascarpone, feta, goat cheese, queso fresco, paneer, halloumi, etc.", 35),
    ("cheese_aged", "Aged and hard cheeses: parmesan, pecorino, cheddar varieties, gruyere, manchego, gouda, aged provolone, asiago, etc.", 35),
    ("cheese_blue", "Blue and specialty cheeses: gorgonzola, roquefort, stilton, brie, camembert, taleggio, fontina, etc.", 25),
    
    # Dairy - Other
    ("dairy_other", "Yogurt, butter, and cultured dairy: Greek yogurt, regular yogurt, kefir, sour cream, crème fraîche, butter varieties, ghee, labneh, etc.", 30),
    
    # Eggs
    ("eggs", "Eggs and egg products: chicken eggs, duck eggs, quail eggs, egg whites, egg yolks, liquid eggs, etc.", 15),
    
    # Grains - Rice (extensive)
    ("rice", "Rice varieties: white rice, brown rice, basmati, jasmine, arborio, sushi rice, wild rice, black rice, red rice, sticky rice, etc.", 30),
    
    # Grains - Pasta & Noodles
    ("pasta", "Pasta shapes: spaghetti, penne, rigatoni, fusilli, farfalle, linguine, fettuccine, lasagna, orzo, orecchiette, gnocchi, etc.", 40),
    ("noodles_asian", "Asian noodles: ramen, udon, soba, rice noodles, glass noodles, egg noodles, lo mein, chow mein, rice vermicelli, etc.", 35),
    
    # Grains - Bread (international)
    ("bread", "Breads and flatbreads: sourdough, baguette, ciabatta, focaccia, pita, naan, roti, tortillas (corn/flour), lavash, injera, challah, brioche, etc.", 50),
    
    # Grains - Flour & Baking
    ("flour", "Flours: all-purpose, bread flour, cake flour, whole wheat, semolina, rice flour, almond flour, coconut flour, chickpea flour (besan), tapioca flour, etc.", 35),
    
    # Grains - Whole Grains
    ("whole_grains", "Whole grains: quinoa, farro, bulgur, barley, oats, millet, buckwheat, couscous, freekeh, amaranth, teff, etc.", 30),
    
    # Legumes (extensive)
    ("legumes_beans", "Beans: black beans, pinto, kidney, cannellini, navy, lima, fava, adzuki, mung, black-eyed peas, etc.", 35),
    ("legumes_lentils", "Lentils and peas: red lentils, green lentils, brown lentils, French lentils, split peas, chickpeas, etc.", 25),
    
    # Nuts & Seeds (extensive)
    ("nuts", "Nuts: almonds, walnuts, pecans, cashews, pistachios, hazelnuts, macadamia, pine nuts, Brazil nuts, chestnuts, peanuts, etc.", 30),
    ("seeds", "Seeds: sesame seeds, sunflower seeds, pumpkin seeds, chia seeds, flax seeds, poppy seeds, hemp seeds, etc.", 25),
    ("nut_butters", "Nut and seed butters: peanut butter, almond butter, tahini, cashew butter, sunflower seed butter, etc.", 20),
    
    # Oils & Vinegars
    ("oils", "Cooking oils: olive oil varieties, vegetable oil, canola, coconut oil, sesame oil, avocado oil, peanut oil, grapeseed, walnut oil, etc.", 30),
    ("vinegars", "Vinegars: balsamic, red wine, white wine, apple cider, rice vinegar, sherry vinegar, champagne vinegar, malt vinegar, etc.", 25),
    
    # Spices - Dried (extensive, subdivided)
    ("spices_whole", "Whole spices: peppercorns (varieties), cinnamon sticks, cardamom pods, cloves, star anise, coriander seeds, cumin seeds, fennel seeds, mustard seeds, etc.", 40),
    ("spices_ground", "Ground spices: paprika (varieties), cumin, coriander, turmeric, cinnamon, ginger, nutmeg, allspice, cayenne, chili powder varieties, etc.", 50),
    ("spice_blends", "Spice blends: garam masala, curry powder, Chinese five spice, za'atar, ras el hanout, berbere, jerk seasoning, Old Bay, Italian seasoning, etc.", 40),
    
    # Condiments & Sauces (extensive)
    ("condiments_western", "Western condiments: ketchup, mustard varieties, mayonnaise, hot sauces, Worcestershire, BBQ sauce, relish, horseradish, etc.", 35),
    ("condiments_asian", "Asian condiments: soy sauce varieties, fish sauce, oyster sauce, hoisin, miso varieties, gochujang, sambal, sriracha, etc.", 40),
    
    # Canned & Jarred
    ("canned", "Canned goods: diced tomatoes, tomato paste, tomato sauce, coconut milk, beans, chickpeas, corn, olives, capers, artichoke hearts, etc.", 40),
    ("broths", "Broths and stocks: chicken broth, beef broth, vegetable broth, bone broth, dashi, etc.", 20),
    
    # Baking Essentials
    ("baking_sweeteners", "Sweeteners: granulated sugar, brown sugar, powdered sugar, honey, maple syrup, molasses, agave, corn syrup, etc.", 25),
    ("baking_leaveners", "Leaveners and baking essentials: baking powder, baking soda, yeast varieties, cream of tartar, etc.", 15),
    ("baking_chocolate", "Chocolate and cocoa: unsweetened chocolate, bittersweet, semisweet, milk chocolate, cocoa powder, cacao nibs, white chocolate, etc.", 25),
    ("baking_extracts", "Extracts and flavorings: vanilla extract, almond extract, lemon extract, peppermint, rose water, orange blossom water, etc.", 20),
]

# =============================================================================
# CUISINE-SPECIFIC CATEGORIES - Unique ingredients by cuisine
# =============================================================================
CUISINE_CATEGORIES = [
    ("cuisine_korean", "Essential Korean cooking ingredients: gochugaru, doenjang, gochujang, ssamjang, Korean chili flakes, perilla leaves, Korean radish, napa cabbage, fernbrake, bellflower root, Korean rice cakes, glass noodles, dried anchovies, kelp, Korean pear, etc.", 50),
    
    ("cuisine_japanese", "Essential Japanese cooking ingredients: mirin, sake, dashi ingredients (kombu, bonito), miso varieties, nori, wakame, shiitake, enoki, shimeji, daikon, shiso, wasabi, pickled ginger, panko, Japanese curry, furikake, etc.", 55),
    
    ("cuisine_chinese", "Essential Chinese cooking ingredients: Shaoxing wine, black vinegar, doubanjiang, fermented black beans, five spice, Sichuan peppercorns, dried chilis, wood ear mushrooms, lily bulbs, lotus root, Chinese sausage, oyster sauce, hoisin, light/dark soy, etc.", 60),
    
    ("cuisine_thai", "Essential Thai cooking ingredients: palm sugar, tamarind paste, galangal, kaffir lime leaves, lemongrass, Thai basil, Thai chilis, shrimp paste, fish sauce, coconut cream, makrut lime, Thai eggplant, pea eggplant, etc.", 45),
    
    ("cuisine_vietnamese", "Essential Vietnamese cooking ingredients: nuoc mam, rice paper, pho herbs, Vietnamese coriander, sawtooth coriander, banana blossom, morning glory, mung bean sprouts, shrimp paste, five spice, annatto seeds, etc.", 40),
    
    ("cuisine_indian", "Essential Indian cooking ingredients: ghee, paneer, garam masala, turmeric, asafoetida, fenugreek (seeds and leaves), mustard oil, curry leaves, tamarind, jaggery, chaat masala, amchur, kashmiri chili, urad dal, chana dal, etc.", 70),
    
    ("cuisine_mediterranean", "Mediterranean ingredients: za'atar, sumac, pomegranate molasses, tahini, labneh, halloumi, preserved lemons, harissa, rose water, orange blossom, pine nuts, filo dough, grape leaves, freekeh, etc.", 50),
    
    ("cuisine_greek", "Greek cooking ingredients: feta varieties, kalamata olives, Greek yogurt, oregano, dill, lemon, phyllo, halloumi, kefalotiri, mastiha, ouzo, grape leaves, etc.", 35),
    
    ("cuisine_italian", "Essential Italian ingredients: San Marzano tomatoes, Parmigiano-Reggiano, Pecorino Romano, prosciutto, pancetta, guanciale, mortadella, '00' flour, arborio rice, balsamic vinegar varieties, mascarpone, ricotta, etc.", 55),
    
    ("cuisine_french", "Essential French cooking ingredients: Dijon mustard, crème fraîche, Gruyère, Comté, herbes de Provence, tarragon, shallots, cognac, Calvados, duck fat, foie gras, escargot, etc.", 45),
    
    ("cuisine_spanish", "Spanish cooking ingredients: saffron, smoked paprika (pimentón), chorizo, Serrano ham, manchego, Mahon, bomba rice, sherry vinegar, piquillo peppers, etc.", 40),
    
    ("cuisine_mexican", "Mexican cooking ingredients: dried chilis (ancho, guajillo, pasilla, chipotle, arbol), masa harina, epazote, Mexican oregano, cotija, queso fresco, Oaxacan cheese, crema, achiote, pepitas, nopales, etc.", 55),
    
    ("cuisine_latin", "Latin American ingredients: aji amarillo, rocoto, huacatay, yuca, plantains, queso blanco, chimichurri herbs, hearts of palm, achiote, black beans, Brazilian cheese bread mix, etc.", 45),
    
    ("cuisine_african", "African cooking ingredients: berbere, ras el hanout, harissa, preserved lemons, injera, teff, palm oil, cassava, plantains, egusi, crayfish (dried), dawadawa, suya spice, etc.", 50),
    
    ("cuisine_middle_eastern", "Middle Eastern ingredients: za'atar, sumac, baharat, dried limes, rosewater, orange blossom, pomegranate molasses, labneh, halloumi, kataifi, mahlab, etc.", 45),
    
    ("cuisine_caribbean", "Caribbean cooking ingredients: scotch bonnet peppers, jerk seasoning, allspice, coconut milk, ackee, callaloo, plantains, cassava, annatto, sofrito base ingredients, etc.", 40),
]

GENERATION_PROMPT = """Generate a comprehensive list of {description}

For each ingredient, provide:
1. name: The canonical/most common name in American English
2. aliases: Array of alternative names (regional variations, British English, common misspellings, abbreviations)
3. default_unit: Most common unit when buying/storing (lb, oz, bunch, head, can, bottle, bag, piece, clove, etc.)

Return as JSON array. Example format:
[
  {{"name": "chicken breast", "aliases": ["chicken breasts", "boneless skinless chicken breast", "BSCB"], "default_unit": "lb"}},
  {{"name": "coriander", "aliases": ["cilantro", "fresh coriander", "Chinese parsley"], "default_unit": "bunch"}}
]

Be comprehensive and specific. Include common variations, cuts, and sizes where relevant.
Generate at least {min_count} items. Return ONLY the JSON array, no other text."""


async def generate_category_ingredients(client: OpenAI, category: str, description: str, min_count: int) -> list[dict]:
    """Generate ingredients for a category using GPT."""
    print(f"  > {category} (target: {min_count})...")
    
    try:
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "You are a culinary expert helping build a comprehensive ingredient database for a kitchen assistant app. Be thorough and include ingredients from diverse culinary traditions."},
                {"role": "user", "content": GENERATION_PROMPT.format(description=description, min_count=min_count)}
            ],
            temperature=0.7,
            max_tokens=8000,
        )
        
        content = response.choices[0].message.content.strip()
        
        # Parse JSON (handle markdown code blocks)
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        
        ingredients = json.loads(content)
        print(f"       + Generated {len(ingredients)} ingredients")
        return ingredients
        
    except json.JSONDecodeError as e:
        print(f"       ! Error parsing JSON: {e}")
        return []
    except Exception as e:
        print(f"       ! Error: {e}")
        return []


async def seed_ingredients():
    """Main seeding function."""
    print("=" * 70)
    print("Comprehensive Ingredient Seeding v2")
    print("=" * 70)
    
    # Initialize clients
    openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    supabase = get_client()
    
    all_ingredients = []
    
    # Generate BASE categories
    print("\n[BASE CATEGORIES]\n")
    for category, description, min_count in BASE_CATEGORIES:
        ingredients = await generate_category_ingredients(
            openai_client, category, description, min_count
        )
        base_cat = category.split("_")[0]
        for ing in ingredients:
            ing["category"] = base_cat
        all_ingredients.extend(ingredients)
    
    # Generate CUISINE-SPECIFIC categories
    print("\n[CUISINE-SPECIFIC CATEGORIES]\n")
    for category, description, min_count in CUISINE_CATEGORIES:
        ingredients = await generate_category_ingredients(
            openai_client, category, description, min_count
        )
        cuisine = category.replace("cuisine_", "")
        for ing in ingredients:
            ing["category"] = f"cuisine_{cuisine}"
        all_ingredients.extend(ingredients)
    
    print(f"\nTotal generated: {len(all_ingredients)} ingredients")
    
    # Deduplicate by name (case-insensitive)
    seen_names = set()
    unique_ingredients = []
    duplicates = 0
    for ing in all_ingredients:
        name_lower = ing["name"].lower().strip()
        if name_lower not in seen_names:
            seen_names.add(name_lower)
            unique_ingredients.append(ing)
        else:
            duplicates += 1
    
    print(f"After deduplication: {len(unique_ingredients)} unique ({duplicates} duplicates removed)")
    
    # Insert into database
    print("\nInserting into database...")
    
    batch_size = 50
    inserted = 0
    errors = 0
    
    for i in range(0, len(unique_ingredients), batch_size):
        batch = unique_ingredients[i:i + batch_size]
        
        records = []
        for ing in batch:
            records.append({
                "name": ing["name"].strip(),
                "aliases": ing.get("aliases", []),
                "category": ing.get("category"),
                "default_unit": ing.get("default_unit"),
            })
        
        try:
            result = supabase.table("ingredients").upsert(
                records,
                on_conflict="name"
            ).execute()
            inserted += len(batch)
            print(f"  + Batch {i // batch_size + 1}/{(len(unique_ingredients) // batch_size) + 1}: {len(batch)} ingredients")
        except Exception as e:
            print(f"  ! Error inserting batch: {e}")
            errors += len(batch)
    
    print(f"\nSeeding complete!")
    print(f"   Inserted: {inserted}")
    print(f"   Errors: {errors}")
    
    # Category breakdown
    print("\nCategory breakdown:")
    category_counts = {}
    for ing in unique_ingredients:
        cat = ing.get("category", "unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1
    
    for cat, count in sorted(category_counts.items()):
        print(f"   {cat}: {count}")
    
    print(f"\n   TOTAL: {sum(category_counts.values())}")


if __name__ == "__main__":
    asyncio.run(seed_ingredients())
