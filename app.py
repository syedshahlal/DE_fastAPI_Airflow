from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from passlib.context import CryptContext
from faker import Faker
import motor.motor_asyncio
import asyncio
import random
import time
import uuid
import json
import logging
from dotenv import load_dotenv
import os
from jose import JWTError, jwt

# Load environment variables
load_dotenv()

# Retrieve environment variables
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
SECRET_KEY = os.getenv("SECRET_KEY", "your_default_secret_key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("fastapi-app")

# Initialize FastAPI app and Faker
app = FastAPI()
fake = Faker()

# MongoDB Configuration
client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
db = client["transaction_db"]
transactions_collection = db["transactions"]

# Create indexes for optimized queries
async def create_indexes():
    await transactions_collection.create_index("transaction_details.timestamp")
    await transactions_collection.create_index("user.email")
    logger.info("MongoDB indexes created.")

# Mount static files
app.mount("/static", StaticFiles(directory="fastAPI_app/static"), name="static")

# Mount templates
templates = Jinja2Templates(directory="fastAPI_app/templates")

# Enable CORS (configure origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for validation
class CreditCard(BaseModel):
    number: str
    expiration_date: str
    provider: str
    security_code: str

class User(BaseModel):
    name: str
    email: EmailStr
    phone_number: str
    address: str
    ip_address: str
    credit_card: CreditCard

class Location(BaseModel):
    city: str
    state: str
    country: str

class TransactionDetails(BaseModel):
    amount: float
    currency: str
    timestamp: float
    merchant: str
    merchant_category: str
    location: Location
    transaction_type: str

class FraudDetection(BaseModel):
    flagged: bool
    reason: Optional[str] = None

class Transaction(BaseModel):
    transaction_id: str
    user: User
    transaction_details: TransactionDetails
    fraud_detection: FraudDetection

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Token data model
class Token(BaseModel):
    access_token: str
    token_type: str


# Initialize password context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Fake user database (for demonstration)
fake_users_db = {
    "user@example.com": {
        "username": "user@example.com",
        "full_name": "John Doe",
        "email": "user@example.com",
        "hashed_password": pwd_context.hash("secret"),
        "disabled": False,
    }
}


# Authentication functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def authenticate_user(email: str, password: str):
    user = fake_users_db.get(email)
    if not user:
        return False
    if not verify_password(password, user["hashed_password"]):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[int] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = time.time() + expires_delta * 60
    else:
        expire = time.time() + ACCESS_TOKEN_EXPIRE_MINUTES * 60
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = fake_users_db.get(email)
    if user is None:
        raise credentials_exception
    return user

# WebSocket Connection Manager with Authentication
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket, token: str):
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email: str = payload.get("sub")
            if email is None or email not in fake_users_db:
                raise JWTError
        except JWTError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected: {websocket.client}")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected: {websocket.client}")
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                self.active_connections.remove(connection)

manager = ConnectionManager()

# Mapping of countries to currencies
COUNTRY_CURRENCY_MAP = {
    "United States": "USD",
    "Canada": "CAD",
    "United Kingdom": "GBP",
    "Germany": "EUR",
    "France": "EUR",
    "Japan": "JPY",
    "Australia": "AUD",
    "India": "INR",
    "Brazil": "BRL",
    "China": "CNY",
    "South Africa": "ZAR",
    "United Arab Emirates": "AED",
    "Saudi Arabia": "SAR",
    "Singapore": "SGD",
    "South Korea": "KRW",
    "Russia": "RUB",
    "Turkey": "Lira",
    # Add more countries and their currencies as needed
}

# List of merchant categories and transaction types
MERCHANT_CATEGORIES = [
    "Electronics",
    "Groceries",
    "Clothing",
    "Restaurants",
    "Travel",
    "Healthcare",
    "Automotive",
    "Entertainment",
    "Utilities",
    "Education",
    "Books",
    "Furniture",
    "Sports",
    "Beauty",
    "Jewelry",
    "Toys",
    "Hardware",
    "Software",
    "Music",
    "Movies",
    "Pet Supplies",
    "Home Improvement",
    "Office Supplies",
    "Gifts",
    "Food Delivery",
    "Subscription Services",
    "Online Services",
    "Fitness",
    "Insurance",
    "Real Estate",
    "Legal Services",
    "Financial Services",
    "Charity",
    "Other"
]

TRANSACTION_TYPES = ["POS", "Online", "ATM Withdrawal", "Mobile Payment", "Recurring Payment"]

# Function to generate a transaction with advanced fraud detection
async def generate_transaction() -> dict:
    country = random.choice(list(COUNTRY_CURRENCY_MAP.keys()))
    currency = COUNTRY_CURRENCY_MAP[country]
    amount = round(random.uniform(5, 10000), 2)
    timestamp = time.time()
    
    # Advanced fraud detection logic
    flagged = False
    reason = ""
    user_activity = random.random()
    
    if amount > 8000:
        flagged = True
        reason = "High Value Transaction"
    elif country not in ["United States", "Canada", "United Kingdom", "Germany", "France", "Japan", "Australia", "India"]:
        flagged = True
        reason = "Unusual Geographical Location"
    elif user_activity < 0.01:  # 1% chance for suspicious activity
        flagged = True
        reason = "Multiple Failed Attempts"
    elif 5000 < amount <= 8000 and random.random() < 0.05:
        flagged = True
        reason = "Suspicious Transaction Pattern"
    
    transaction = {
        "transaction_id": str(uuid.uuid4()),
        "user": {
            "name": fake.name(),
            "email": fake.email(),
            "phone_number": fake.phone_number(),
            "address": fake.address().replace("\n", ", "),
            "ip_address": fake.ipv4_public(),
            "credit_card": {
                "number": fake.credit_card_number(),
                "expiration_date": fake.credit_card_expire(),
                "provider": fake.credit_card_provider(),
                "security_code": fake.credit_card_security_code()
            }
        },
        "transaction_details": {
            "amount": amount,
            "currency": currency,
            "timestamp": timestamp,
            "merchant": fake.company(),
            "merchant_category": random.choice(MERCHANT_CATEGORIES),
            "location": {
                "city": fake.city(),
                "state": fake.state(),
                "country": country,
            },
            "transaction_type": random.choice(TRANSACTION_TYPES),
        },
        "fraud_detection": {
            "flagged": flagged,
            "reason": reason if flagged else None
        }
    }
    return transaction

# Background task to generate transactions
async def transaction_generator():
    try:
        while True:
            transaction = await generate_transaction()
            # Insert into MongoDB
            await transactions_collection.insert_one(transaction)
            logger.info(f"Inserted transaction {transaction['transaction_id']}")
            # Broadcast to WebSocket clients
            await manager.broadcast(json.dumps(transaction))
            await asyncio.sleep(random.uniform(0.5, 3))  # Random delay between transactions
    except asyncio.CancelledError:
        logger.info("Transaction generator task cancelled.")

# Startup event to initiate background transaction generation
@app.on_event("startup")
async def startup_event():
    await create_indexes()
    app.state.transaction_task = asyncio.create_task(transaction_generator())
    logger.info("Transaction generator started.")

# Shutdown event to gracefully terminate background tasks
@app.on_event("shutdown")
async def shutdown_event():
    app.state.transaction_task.cancel()
    await app.state.transaction_task
    logger.info("Transaction generator stopped.")

# Serve index.html
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, current_user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("index.html", {"request": request, "user": current_user})

# Serve transaction data with pagination
@app.get("/transactions", response_model=List[Transaction])
async def get_transactions(limit: int = 100, skip: int = 0, current_user: dict = Depends(get_current_user)):
    cursor = transactions_collection.find().sort("transaction_details.timestamp", -1).skip(skip).limit(limit)
    transactions = []
    async for document in cursor:
        transactions.append(Transaction(**document))
    return transactions

# Token endpoint for user authentication
@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        logger.warning(f"Failed login attempt for user: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user["email"]}, expires_delta=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    logger.info(f"User {user['email']} logged in successfully.")
    return {"access_token": access_token, "token_type": "bearer"}

# WebSocket endpoint for real-time transactions with token authentication
@app.websocket("/ws/transactions")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(None)):
    if token is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await manager.connect(websocket, token)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo the received message (if needed)
            await websocket.send_text(f"Message received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Error handler for 404 Not Found
@app.exception_handler(404)
async def not_found(request: Request, exc):
    return JSONResponse(status_code=404, content={"message": "Resource not found"})

# Run the application
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
