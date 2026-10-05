# ------------------------------------------------------------
#  "What Can I Cook?" - Fridge Tool  (Version 1)
#  Take a picture of your fridge -> get recipes, macros,
#  cook times, and a meal plan for the rest of the week.
#
#  Run it with:   streamlit run fridge_app.py
# ------------------------------------------------------------

import json                      # turns the AI's text answer into Python data
import datetime                  # figures out what day it is today
import time                      # lets the app wait a few seconds before retrying
import streamlit as st           # makes the web page
from google import genai         # talks to Google's Gemini AI
from google.genai import types


# ---------- PAGE SETUP ----------
st.set_page_config(page_title="What Can I Cook?", page_icon="🍳", layout="wide")
st.title("🍳 What Can I Cook?")
st.write("Snap a photo of your fridge and get recipes, macros, and a meal plan for the week.")


# ---------- SIDEBAR: AI SETTINGS ----------
st.sidebar.header("⚙️ Settings")

# Online, the key is hidden in Streamlit's "Secrets" box.
# On your own computer, there are no secrets, so the sidebar asks for it.
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ AI key loaded")
except Exception:
    api_key = st.sidebar.text_input("Gemini API key", type="password",
                                    help="Get a free key at aistudio.google.com")

model_name = st.sidebar.text_input("AI model", value="gemini-3.8-flash")


# ---------- HELPER: ASK THE AI ----------
def ask_ai(prompt, image_bytes=None, image_type=None):
    """Sends a question (and maybe a picture) to Gemini and returns its answer as Python data."""
    client = genai.Client(api_key=api_key)

    contents = []
    if image_bytes is not None:
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type=image_type))
    contents.append(prompt)

    # Try the chosen model first, then backup models if Google is busy.
    models_to_try = [model_name] + [m for m in BACKUP_MODELS if m != model_name]
    last_error = None

    for model in models_to_try:
        for attempt in range(3):                      # try each model up to 3 times
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                return json.loads(response.text)  # it worked!
            except Exception as error:
                last_error = error
                message = str(error)
                busy = "503" in message or "429" in message or "UNAVAILABLE" in message
                missing = "404" in message or "NOT_FOUND" in message
                if missing:
                    break                             # model doesn't exist, go to next model
                if not busy:
                    raise                             # some other problem, show it
                time.sleep(2 * (attempt + 1))         # busy: wait 2s, 4s, 6s, then retry

    raise Exception(f"Google's AI is very busy right now. Wait a minute and try again. ({last_error})")


# ---------- HELPER: WHICH DAYS ARE LEFT THIS WEEK? ----------
def days_left_in_week():
    """Returns a list like ['Thursday', 'Friday', 'Saturday', 'Sunday']."""
    today = datetime.date.today()
    days = []
    for i in range(7 - today.weekday()):          # Monday=0 ... Sunday=6
        day = today + datetime.timedelta(days=i)
        days.append(day.strftime("%A"))
    return days


# ---------- MEMORY (so the page doesn't forget between clicks) ----------
if "ingredients" not in st.session_state:
    st.session_state.ingredients = ""
if "results" not in st.session_state:
    st.session_state.results = None


# ============================================================
#  STEP 1: TAKE OR UPLOAD A PHOTO
# ============================================================
st.header("1️⃣ Show me your fridge")
col1, col2 = st.columns(2)
with col1:
    camera_photo = st.camera_input("Take a picture")
with col2:
    uploaded_photo = st.file_uploader("...or upload one", type=["jpg", "jpeg", "png", "webp"])

photo = camera_photo or uploaded_photo

if photo and st.button("🔍 Find my ingredients"):
    if not api_key:
        st.error("Paste your Gemini API key in the sidebar first.")
    else:
        with st.spinner("Looking in your fridge..."):
            try:
                answer = ask_ai(
                    'List every food ingredient you can see in this photo. '
                    'Reply in JSON like: {"ingredients": ["eggs", "milk", "cheddar cheese"]}',
                    image_bytes=photo.getvalue(),
                    image_type=photo.type,
                )
                st.session_state.ingredients = ", ".join(answer["ingredients"])
            except Exception as error:
                st.error(f"Something went wrong: {error}")


# ============================================================
#  STEP 2: CHECK THE INGREDIENT LIST (the AI can make mistakes!)
# ============================================================
st.header("2️⃣ Check your ingredients")
st.caption("Fix anything the AI got wrong, or just type your ingredients here yourself.")
st.session_state.ingredients = st.text_area(
    "Ingredients (separate with commas)", value=st.session_state.ingredients)


# ============================================================
#  STEP 3: GET RECIPES + MEAL PLAN
# ============================================================
st.header("3️⃣ Get recipes and a meal plan")

if st.button("🍽️ Make my recipes and meal plan"):
    if not api_key:
        st.error("Paste your Gemini API key in the sidebar first.")
    elif not st.session_state.ingredients.strip():
        st.error("Add some ingredients first.")
    else:
        days = days_left_in_week()
        prompt = f"""
        I have these ingredients: {st.session_state.ingredients}.
        Assume I also have basic pantry items (salt, pepper, oil, water).

        1. Suggest 6 recipes I can make mostly from these ingredients.
        2. For each recipe, estimate calories, protein, carbs, and fat PER SERVING,
           and how many minutes it takes to make.
        3. Make a meal plan for these days: {", ".join(days)}.
           Give each day a breakfast, lunch, and dinner using the recipes.

        Reply ONLY in this JSON format:
        {{
          "recipes": [
            {{
              "name": "Cheese Omelette",
              "minutes": 10,
              "servings": 1,
              "calories": 350,
              "protein_g": 22,
              "carbs_g": 2,
              "fat_g": 28,
              "ingredients_used": ["eggs", "cheddar cheese"],
              "missing": [],
              "steps": ["Whisk eggs", "Cook in pan", "Add cheese and fold"]
            }}
          ],
          "meal_plan": [
            {{"day": "Thursday", "breakfast": "Cheese Omelette", "lunch": "...", "dinner": "..."}}
          ]
        }}
        """
        with st.spinner("Cooking up ideas..."):
            try:
                st.session_state.results = ask_ai(prompt)
            except Exception as error:
                st.error(f"Something went wrong: {error}")


# ============================================================
#  SHOW THE RESULTS
# ============================================================
results = st.session_state.results

if results:
    # ----- Recipe cards -----
    st.subheader("📖 Recipes you can make")
    st.caption("Macros and times are AI estimates, not exact numbers.")

    card_columns = st.columns(2)
    for number, recipe in enumerate(results["recipes"]):
        with card_columns[number % 2]:              # alternate left / right column
            with st.container(border=True):
                st.markdown(f"### {recipe['name']}")
                st.write(f"⏱️ {recipe['minutes']} min  •  🍽️ {recipe['servings']} serving(s)")

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Calories", recipe["calories"])
                c2.metric("Protein", f"{recipe['protein_g']} g")
                c3.metric("Carbs", f"{recipe['carbs_g']} g")
                c4.metric("Fat", f"{recipe['fat_g']} g")

                st.write("**Uses:** " + ", ".join(recipe["ingredients_used"]))
                if recipe["missing"]:
                    st.warning("**Missing:** " + ", ".join(recipe["missing"]))

                with st.expander("Show steps"):
                    for step_number, step in enumerate(recipe["steps"], start=1):
                        st.write(f"{step_number}. {step}")

    # ----- Meal plan table -----
    st.subheader("📅 Your meal plan for the rest of the week")
    st.table(results["meal_plan"])
