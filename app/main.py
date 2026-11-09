"""FastAPI uygulaması. Çalıştırmak için: uvicorn app.main:app --reload"""

from fastapi import FastAPI

from app.analiz.api import router as analiz_router
from app.belge.api import router as belge_router
from app.dava.api import kullanici_router, muvekkil_router
from app.dava.api import router as dava_router
from app.kimlik.api import router as kimlik_router
from app.kimlik.yonetim_api import router as yonetim_router

app = FastAPI(title="LawTrace")
app.include_router(kimlik_router)
app.include_router(dava_router)
app.include_router(muvekkil_router)
app.include_router(kullanici_router)
app.include_router(belge_router)
app.include_router(analiz_router)
app.include_router(yonetim_router)
