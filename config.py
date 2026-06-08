import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-123")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    # هنضيف هنا قدام الـ Redis والـ Pinecone configurations