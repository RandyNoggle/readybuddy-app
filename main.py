"""
ReadyBuddy Code-Based MVP

This script implements a simple web application for the ReadyBuddy
emergency‑preparedness micro‑learning tool. It uses FastAPI for routing
and Jinja2 for templating. The application exposes pages for
onboarding, viewing micro‑learning modules, taking quizzes, and
managing an emergency kit checklist. All data is stored in memory for
simplicity—no external database is required. Use this as a starting
point for a more robust, database‑backed solution.
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from typing import List, Dict, Optional
# Note: SessionMiddleware is commented out because itsdangerous is not installed
# from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates


app = FastAPI(title="ReadyBuddy")

# Define base directories up front so they can be used throughout the module.  We
# calculate BASE_DIR relative to this file, and then derive the template
# directory and static asset directory from it. By defining these paths early,
# other components (like the database path) can reference them without raising
# NameError.
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# ------------------------------ Database Setup ------------------------------
# We use Python's built‑in sqlite3 module to persist data across sessions. This
# avoids any external dependencies and works well on free hosting tiers. The
# database stores user profiles created via the onboarding form and quiz results
# for each module. When the server starts, we ensure the tables exist.
import sqlite3

# Database file is stored alongside the application code. Using .as_posix() ensures
# SQLite receives a string path. The database will persist between requests
# within the same server instance.
DB_PATH = (BASE_DIR / "app.db").as_posix()


def init_db() -> None:
    """
    Initialize the SQLite database. If the tables for user profiles and
    quiz results do not exist, create them. This function is idempotent and
    will not overwrite existing data.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Table for storing onboarding responses. Each user is assigned a unique
    # integer primary key. We store the number of household members, the
    # location string, and the self‑assessed skill level.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_size INTEGER,
            location TEXT,
            skill_level TEXT
        )
        """
    )
    # Table for storing quiz results. Each record captures which user took
    # which module and whether they answered correctly (1) or not (0). A
    # timestamp column automatically records when the result was saved.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            module_id INTEGER,
            score INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES user_profiles(id)
        )
        """
    )
    conn.commit()
    conn.close()


# Ensure the database is ready when the module is imported. If you're running
# this in a serverless environment like Replit or Vercel, the database file
# will persist across requests as long as the instance remains active.
init_db()

# Add session middleware to enable per‑user storage of onboarding info
# SessionMiddleware would normally allow us to persist onboarding data per user,
# but it's commented out here because the itsdangerous dependency isn't
# available in this environment. You can re‑enable it after installing
# itsdangerous by uncommenting the import and the line below.
# app.add_middleware(SessionMiddleware, secret_key="change_this_secret_key")

# The template and static directories are defined near the top of this file.
# Mount the static directory (for CSS, images, etc.). You can place additional
# assets in readybuddy_code/static and they will be served automatically. For
# styling we rely primarily on Bootstrap via CDN.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# ------------------------------ Data Models ------------------------------
class Module:
    """
    Represents a micro‑learning module with a quiz. Each module includes a
    title, description, detailed content, a quiz question with options and
    correct answer, and optional media. If provided, `image` should be the
    filename of a PNG in the static directory. If `video_link` is provided,
    it should point to an external, royalty‑free or government‑hosted video
    that illustrates the subject matter. By keeping media optional, the
    application can fall back to text‑only lessons when no graphic or
    video is available.
    """

    def __init__(
        self,
        id: int,
        title: str,
        description: str,
        content: str,
        question_text: str,
        options: List[str],
        answer: str,
        image: Optional[str] = None,
        video_link: Optional[str] = None,
    ) -> None:
        self.id = id
        self.title = title
        self.description = description
        self.content = content
        self.question = {
            "text": question_text,
            "options": options,
            "answer": answer,
        }
        self.image = image
        self.video_link = video_link


class ChecklistItem:
    """Represents a single emergency kit checklist item."""

    def __init__(self, id: int, name: str, affiliate_url: str):
        self.id = id
        self.name = name
        self.affiliate_url = affiliate_url


# Predefined modules and checklist items. In a real application these
# could be stored in a database or pulled from an external API.
modules: List[Module] = [
    # Core preparedness topics
    Module(
        id=1,
        title="Home Emergency Kit",
        description="Build a basic emergency kit for your home.",
        content=(
            "A well‑stocked emergency kit is critical. Ensure you have at least a three‑day supply of non‑perishable food, "
            "one gallon of water per person per day, a flashlight with extra batteries, a battery‑powered or hand‑crank radio, "
            "first aid supplies, a whistle to signal for help, and local maps. Rotate food and water every six months."
        ),
        question_text="What is the recommended minimum amount of water to store per person per day?",
        options=["Half a gallon", "One gallon", "Two gallons"],
        answer="One gallon",
    ),
    Module(
        id=2,
        title="Fire Safety & Prevention",
        description="Learn how to reduce fire risks and respond effectively.",
        content=(
            "Install smoke detectors on every level of your home and test them monthly. Practice a family fire escape plan twice a year. "
            "Keep a fire extinguisher in the kitchen and know how to use it. Never leave cooking unattended."
        ),
        question_text="How often should you test your smoke detectors?",
        options=["Every week", "Every month", "Every year"],
        answer="Every month",
    ),
    Module(
        id=3,
        title="Seismic Safety Basics",
        description="Secure your home and identify safe spots before an earthquake.",
        content=(
            "Secure heavy furniture and appliances to walls, and store breakable items on low shelves. "
            "Identify safe spots in each room, like under sturdy tables or against interior walls. Practice drills so everyone knows where to go."
        ),
        question_text="Where is a safe place to be during an earthquake?",
        options=["Near exterior windows", "Under a sturdy table", "In a doorway"],
        answer="Under a sturdy table",
    ),
    Module(
        id=4,
        title="First Aid Basics",
        description="Understand essential first aid techniques.",
        content=(
            "Learn how to perform CPR, treat minor cuts and burns, and recognize signs of shock. "
            "Always have a well‑stocked first aid kit and take a certified course to refresh your skills annually."
        ),
        question_text="Which of the following is recommended for treating a minor burn?",
        options=["Apply ice directly", "Use cool water and cover with a sterile gauze", "Pop any blisters"],
        answer="Use cool water and cover with a sterile gauze",
    ),
    Module(
        id=5,
        title="Evacuation Planning",
        description="Create and practice an evacuation plan.",
        content=(
            "Identify multiple evacuation routes from your home and community. Choose meeting points and communication plans. "
            "Keep your vehicle fueled, and have a go‑bag ready with essential documents, cash, and supplies."
        ),
        question_text="Why is it important to have multiple evacuation routes?",
        options=["In case roads are blocked", "It isn’t important", "To increase travel time"],
        answer="In case roads are blocked",
    ),
    # Additional hazard and survival modules with images and recommended videos
    Module(
        id=6,
        title="Drop, Cover & Hold On",
        description="Learn how to protect yourself during an earthquake.",
        content=(
            "Earthquakes strike without warning. To protect yourself, follow the 'Drop, Cover, and Hold On' procedure: drop to the ground before the quake drops you, "
            "take cover under a sturdy table or desk (or cover your head and neck with your arms if no shelter is available), and hold on until the shaking stops. "
            "Secure heavy items in your home, such as bookcases and appliances, to prevent them from falling. Prepare an emergency kit and practice drills with your family."
        ),
        question_text="What should you do during an earthquake?",
        options=["Run outside", "Drop, Cover, and Hold On", "Stand in a doorway"],
        answer="Drop, Cover, and Hold On",
        image="earthquake.png",
        video_link="https://www.shakeout.org/dropcoverholdon/"
    ),
    Module(
        id=7,
        title="Tsunami Preparedness",
        description="Understand tsunami warning signs and how to respond quickly.",
        content=(
            "If you are near the coast and feel strong or long shaking, hear a loud roar from the ocean, or notice the water suddenly recede, a tsunami could be coming. "
            "Have multiple ways to receive warnings (NOAA Weather Radio, text alerts) and know your community’s evacuation routes to high ground. "
            "Create a family emergency plan, practice walking your evacuation routes, and prepare a portable disaster supplies kit."
        ),
        question_text="After feeling strong shaking near the coast, what should you do?",
        options=["Wait for an official alert", "Immediately go to high ground", "Call your neighbors"],
        answer="Immediately go to high ground",
        image="tsunami.png",
        video_link="https://www.weather.gov/jetstream/tsunami"
    ),
    Module(
        id=8,
        title="Urban Survival Basics",
        description="Tips for staying safe and prepared in city environments.",
        content=(
            "Urban emergencies can include power outages, civil unrest, and infrastructure failures. Maintain situational awareness and have a family communication plan. "
            "Keep a get‑home bag with water, snacks, first aid supplies, and sturdy shoes. Know how to shut off utilities and identify safe shelter locations. "
            "Follow guidance from local authorities and stay informed through reliable news sources."
        ),
        question_text="Which of the following is NOT recommended for urban survival?",
        options=["Keep a get-home bag", "Have a family communication plan", "Ignore local authorities"],
        answer="Ignore local authorities",
        image="urban.png",
        video_link="https://www.ready.gov/power-outages"
    ),
    Module(
        id=9,
        title="Rural Survival Basics",
        description="Fundamental skills for survival in wilderness and rural areas.",
        content=(
            "In rural or wilderness settings, your priorities are shelter, water, fire, and food. Learn to locate and purify water from natural sources, build a simple shelter, and start a fire safely. "
            "Carry a map and compass, and know basic navigation. Understand local flora and fauna, and always let someone know your travel plans before venturing out."
        ),
        question_text="What is the priority when lost in a rural wilderness?",
        options=["Posting on social media", "Finding a safe water source", "Collecting souvenirs"],
        answer="Finding a safe water source",
        image="rural.png",
        video_link="https://www.ready.gov/wilderness"
    ),
]

checklist_items: List[ChecklistItem] = [
    ChecklistItem(1, "Water (one gallon per person per day)", "https://www.amazon.com/dp/B0B5YYR5J9"),
    ChecklistItem(2, "Non‑perishable food for three days", "https://www.amazon.com/dp/B084QVTVGN"),
    ChecklistItem(3, "Battery‑powered or hand‑crank radio", "https://www.amazon.com/dp/B07PVX7LH8"),
    ChecklistItem(4, "Flashlight & extra batteries", "https://www.amazon.com/dp/B004US6R7G"),
    ChecklistItem(5, "First aid kit", "https://www.amazon.com/dp/B01FSTYHXW"),
    ChecklistItem(6, "Whistle to signal for help", "https://www.amazon.com/dp/B000X25YTA"),
]

# ------------------------------ Resources ------------------------------
# Links to volunteer organizations and programs that support community
# preparedness. These descriptions are drawn from official sources so
# users understand why each program is important and how to get involved.
resources: List[Dict[str, str]] = [
    {
        "name": "SERV‑OR",
        "url": "https://www.serv-or.org",
        "description": (
            "The State Emergency Registry of Volunteers in Oregon (SERV‑OR) is a statewide registry of pre‑credentialed "
            "health care professionals who volunteer during emergencies with significant health impacts. Sponsored by the Oregon Public Health Division in "
            "partnership with the Medical Reserve Corps, SERV‑OR uses a secure database to register, credential and alert volunteers so they can be called on to help when disaster strikes"
        ),
    },
    {
        "name": "Medical Reserve Corps (MRC)",
        "url": "https://serv-or.org/ResourceLibrary/Pages/Medical-Reserve-Corps.aspx",
        "description": (
            "The Medical Reserve Corps is a national network of licensed health care and medical professionals who volunteer to help during disasters and emergency "
            "preparedness activities. Local MRC units, such as those in Multnomah, Clackamas and Washington counties, recruit doctors, nurses, pharmacists and other licensed providers to assist with community reception centers, vaccination clinics, disease investigation, contact tracing, emergency call centers and public education"
        ),
    },
    {
        "name": "Community Emergency Response Team (CERT)",
        "url": "https://servewashington.wa.gov/programs/cert-community-emergency-response-team",
        "description": (
            "CERTs are volunteer teams that support professional first responders. Members learn basic disaster response skills—fire safety, light search and rescue and "
            "medical operations—and teach people in their neighborhoods how to prepare for disasters. During emergencies, CERT volunteers can provide first aid, check on neighbors, support local emergency centers, and connect survivors to resources"
        ),
    },
    {
        "name": "OregonServes & ORVID",
        "url": "https://www.oregon.gov/oregonserves/emergency-response/Pages/default.aspx",
        "description": (
            "OregonServes is the state service commission that partners in Oregon’s Emergency Response Plan for managing volunteers and donations. "
            "It increases response and recovery resources by administering the Oregon Volunteers in Disaster (ORVID) system—a free, statewide volunteer management tool "
            "that helps emergency managers track and credential volunteers and helps volunteers connect to opportunities in their communities"
        ),
    },
]


# ------------------------------- Routes -------------------------------
@app.get("/")
async def home(request: Request):
    """
    Display the onboarding form. In this simplified implementation we
    don’t persist onboarding data, so the form is always shown on the
    homepage. Once submitted, users are redirected to the modules page.
    """
    return templates.TemplateResponse("onboarding.html", {"request": request})


@app.get("/onboarding")
async def submit_onboarding(request: Request):
    """
    Handle onboarding form submission. We expect the form fields to be
    delivered via the query string (family_size, location, skill_level).
    A new record is inserted into the `user_profiles` table and the
    corresponding user ID is stored in a cookie. The user is then
    redirected to the modules list. If any fields are missing or invalid,
    we still redirect but do not persist data.
    """
    # Extract query parameters. Defaults are None if not provided.
    family_size_raw = request.query_params.get("family_size")
    location = request.query_params.get("location")
    skill_level = request.query_params.get("skill_level")
    user_id = None
    # Basic validation: ensure all parameters are present and
    # family_size is an integer greater than zero.
    try:
        if family_size_raw and location and skill_level:
            family_size = int(family_size_raw)
            if family_size > 0:
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO user_profiles (family_size, location, skill_level) VALUES (?, ?, ?)",
                    (family_size, location, skill_level),
                )
                user_id = cur.lastrowid
                conn.commit()
                conn.close()
    except Exception:
        # In case of parsing or database errors, ignore and proceed
        pass
    # Redirect to modules page with a cookie if we obtained a user_id
    response = RedirectResponse(url="/modules", status_code=303)
    if user_id is not None:
        # Store the user_id in a cookie so we can associate quiz results later.
        # Cookies are stored as strings. Set a max_age of 30 days.
        response.set_cookie(
            key="user_id",
            value=str(user_id),
            max_age=60 * 60 * 24 * 30,
            httponly=True,
        )
    return response


@app.get("/modules")
async def modules_list(request: Request):
    """List all available micro‑learning modules."""
    return templates.TemplateResponse("modules.html", {"request": request, "modules": modules})


@app.get("/modules/{module_id}")
async def module_detail(module_id: int, request: Request):
    """Show the details for a single module, including its quiz."""
    module = next((m for m in modules if m.id == module_id), None)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    return templates.TemplateResponse("module_detail.html", {
        "request": request,
        "module": module,
    })


@app.get("/modules/{module_id}/quiz")
async def submit_quiz(module_id: int, request: Request):
    """
    Evaluate the user's quiz answer and display the result. The form uses
    the GET method so the selected option is passed as a query
    parameter. If no option is provided, the user is redirected back to
    the module detail page. If a user_id cookie is present, we record
    the quiz result (1 for correct, 0 for incorrect) in the database.
    """
    module = next((m for m in modules if m.id == module_id), None)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    selected_option: Optional[str] = request.query_params.get("selected_option")
    if not selected_option:
        return RedirectResponse(url=f"/modules/{module_id}", status_code=303)
    correct = selected_option == module.question["answer"]
    # Persist result if we have a user_id cookie
    user_id_str = request.cookies.get("user_id")
    if user_id_str is not None:
        try:
            user_id = int(user_id_str)
            score = 1 if correct else 0
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO quiz_results (user_id, module_id, score) VALUES (?, ?, ?)",
                (user_id, module_id, score),
            )
            conn.commit()
            conn.close()
        except Exception:
            # Ignore any errors related to database operations
            pass
    return templates.TemplateResponse(
        "quiz_result.html",
        {
            "request": request,
            "module": module,
            "selected": selected_option,
            "correct": correct,
        },
    )


@app.get("/checklist")
async def view_checklist(request: Request):
    """Display the emergency kit checklist."""
    return templates.TemplateResponse("checklist.html", {
        "request": request,
        "items": checklist_items,
    })


@app.get("/resources")
async def resources_page(request: Request):
    """
    Display a page with descriptions and links to volunteer programs and
    organizations such as SERV‑OR, the Medical Reserve Corps, Community Emergency
    Response Teams (CERT) and OregonServes/ORVID. Each entry in the
    `resources` list contains a name, description and URL. Adding a new
    resource is as simple as appending to the list above.
    """
    return templates.TemplateResponse("resources.html", {
        "request": request,
        "resources": resources,
    })