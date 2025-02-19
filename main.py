from fastapi import FastAPI, Depends, File, UploadFile, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import re
import shutil
from pathlib import Path

DATABASE_URL = "sqlite:///./chatapp.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

templates = Jinja2Templates(directory="templates")
app = FastAPI()

# Database Models
class Model(Base):
    __tablename__ = "models"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)

class RoutingRule(Base):
    __tablename__ = "routing_rules"
    id = Column(Integer, primary_key=True, index=True)
    original_model = Column(String)
    regex_pattern = Column(String)
    redirect_model = Column(String)

class FileRoutingRule(Base):
    __tablename__ = "file_routing_rules"
    id = Column(Integer, primary_key=True, index=True)
    file_type = Column(String, unique=True)
    redirect_provider = Column(String)
    redirect_model = Column(String)

Base.metadata.create_all(bind=engine)

# Ensure models are added to the database
def initialize_models():
    db = SessionLocal()
    existing_models = {m.name for m in db.query(Model).all()}
    default_models = ["openai/gpt-3.5", "anthropic/claude-v1", "gemini/gemini-alpha"]
    for model_name in default_models:
        if model_name not in existing_models:
            db.add(Model(name=model_name))
    db.commit()
    db.close()

initialize_models()

# Dependency for DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Routes
@app.get("/models", response_model=list[str])
def list_models(db: Session = Depends(get_db)):
    return [model.name for model in db.query(Model).all()]

@app.post("/v1/chat/completions")
def chat_completions(provider: str = Form(...), model: str = Form(...), prompt: str = Form(...), db: Session = Depends(get_db)):
    models = {m.name for m in db.query(Model).all()}
    if model not in models:
        return {"error": "Model not supported"}

    for rule in db.query(RoutingRule).all():
        if re.search(rule.regex_pattern, prompt, re.IGNORECASE):
            model = rule.redirect_model
            break

    responses = {
        "openai/gpt-3.5": "OpenAI: Processed your prompt with advanced language understanding.",
        "anthropic/claude-v1": "Anthropic: Your prompt has been interpreted with ethical AI principles.",
        "gemini/gemini-alpha": "Gemini: Your request has been processed using next-gen AI."
    }
    return {"provider": provider, "model": model, "response": responses.get(model, "Response not available.")}

@app.get("/", response_class=HTMLResponse)
def home_page():
    return templates.TemplateResponse("index.html", {"request": {}})

@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return templates.TemplateResponse("admin.html", {"request": {}})

@app.post("/upload/")
def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    file_ext = file.filename.split(".")[-1].lower()
    file_path = upload_dir / file.filename
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    rule = db.query(FileRoutingRule).filter(FileRoutingRule.file_type == file_ext).first()
    if rule:
        return {
            "filename": file.filename,
            "provider": rule.redirect_provider,
            "model": rule.redirect_model,
            "response": f"{rule.redirect_provider}: File processed with AI model {rule.redirect_model}."
        }
    return {"filename": file.filename, "response": "File uploaded successfully."}

@app.post("/admin/add_regex")
def add_regex_rule(original_model: str = Form(...), regex_pattern: str = Form(...), redirect_model: str = Form(...), db: Session = Depends(get_db)):
    new_rule = RoutingRule(original_model=original_model, regex_pattern=regex_pattern, redirect_model=redirect_model)
    db.add(new_rule)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/admin/rules")
def get_regex_rules(db: Session = Depends(get_db)):
    return db.query(RoutingRule).all()

@app.post("/admin/add_file_routing")
def add_file_routing_rule(
        file_type: str = Form(...),
        redirect_provider: str = Form(...),
        redirect_model: str = Form(...),
        db: Session = Depends(get_db)
):
    new_rule = FileRoutingRule(
        file_type=file_type,
        redirect_provider=redirect_provider,
        redirect_model=redirect_model
    )
    db.add(new_rule)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/admin/file_rules")
def get_file_routing_rules(db: Session = Depends(get_db)):
    return db.query(FileRoutingRule).all()