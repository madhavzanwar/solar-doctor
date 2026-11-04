from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")


# Models
class DemoRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: str
    company: str
    role: Optional[str] = ""
    message: Optional[str] = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class DemoRequestCreate(BaseModel):
    name: str
    email: str
    company: str
    role: Optional[str] = ""
    message: Optional[str] = ""

class ContactMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: str
    subject: str
    message: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ContactMessageCreate(BaseModel):
    name: str
    email: str
    subject: str
    message: str

class ManifestAsset(BaseModel):
    filename: str
    description: str
    alt_text: str
    placement: str
    og_title: Optional[str] = None
    og_description: Optional[str] = None


# Routes
@api_router.get("/")
async def root():
    return {"message": "Axalon Systems API"}

@api_router.post("/demo-requests", response_model=DemoRequest)
async def create_demo_request(input_data: DemoRequestCreate):
    demo = DemoRequest(**input_data.model_dump())
    doc = demo.model_dump()
    await db.demo_requests.insert_one(doc)
    doc.pop("_id", None)
    return DemoRequest(**doc)

@api_router.get("/demo-requests", response_model=List[DemoRequest])
async def get_demo_requests():
    requests = await db.demo_requests.find({}, {"_id": 0}).to_list(1000)
    return requests

@api_router.post("/contact", response_model=ContactMessage)
async def create_contact_message(input_data: ContactMessageCreate):
    msg = ContactMessage(**input_data.model_dump())
    doc = msg.model_dump()
    await db.contact_messages.insert_one(doc)
    doc.pop("_id", None)
    return ContactMessage(**doc)

@api_router.get("/manifest")
async def get_manifest():
    return {
        "project": "Axalon Systems — Brand Visuals & Web Hero Suite",
        "domain": "axalonsystems.com",
        "palette": {
            "bg": "#0B0D10",
            "bg2": "#111318",
            "surface": "#161A20",
            "primary": "#00D1B2",
            "secondary": "#6EE7F9",
            "text": "#E5E7EB",
            "divider": "rgba(255,255,255,0.08)"
        },
        "fonts": ["Inter", "Space Grotesk", "JetBrains Mono"],
        "og": {
            "title": "Axalon Systems -- Autonomous inspection drones",
            "description": "AI-enabled, modular UAS for precise data capture and automated reporting -- starting with solar asset inspections."
        },
        "meta_keywords": "autonomous drone inspection, LiDAR drone mapping, drone solar park inspection India, industrial drone autonomy, defense-grade autonomous drones India",
        "assets": [
            {
                "key": "hero_photoreal",
                "description": "Primary hero -- solar park overflight with drone and LiDAR overlay",
                "alt_text": "Axalon Systems inspection drone flying over a solar farm with LiDAR overlay, illustrating automated inspection and anomaly detection.",
                "placement": "home_hero"
            },
            {
                "key": "lidar_analytical",
                "description": "LiDAR point cloud overhead analytical hero",
                "alt_text": "Top-down aerial view of solar park with LiDAR point cloud overlay showing detected anomalies.",
                "placement": "product_hero"
            },
            {
                "key": "isometric_render",
                "description": "Isometric technical render of Axalon UAS with labeled components",
                "alt_text": "Isometric studio render of Axalon drone showing modular payload bay with LiDAR, thermal, RGB camera, and onboard AI compute module.",
                "placement": "product_page"
            }
        ],
        "gsap_config": {
            "default_duration": 0.9,
            "ease": "power2.out",
            "stagger": 0.09,
            "parallax": {
                "background": {"translateY": "-6%"},
                "midground": {"translateY": "-12%"},
                "foreground": {"translateY": "-18%"}
            }
        }
    }


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
