"""Dil modeli sağlayıcıları. Analiz kodu yalnızca DilModeli arayüzünü bilir.

Şimdilik yalnızca yerel Ollama var (127.0.0.1, veri bilgisayardan çıkmaz). Bulut
sağlayıcısı eklenecekse aynı arayüzle eklenir; hangi sağlayıcının hangi hukuki
dayanakla kullanılabileceği docs/ altındaki KVKK karşılaştırma belgesindedir.
"""

import json
import os
from typing import Protocol

import httpx


class ModelHatasi(RuntimeError):
    pass


class DilModeli(Protocol):
    saglayici: str
    model: str

    def json_tamamla(self, sistem: str, kullanici: str, sema: dict) -> dict:
        """Verilen JSON şemasına uyan yanıtı sözlük olarak döndürür."""
        ...


def yerel_modeller(adres: str | None = None) -> list[str] | None:
    """Bu bilgisayardaki Ollama'da kurulu modeller; sunucuya ulaşılamazsa None."""
    adres = adres or os.environ.get("OLLAMA_ADRESI", "http://127.0.0.1:11434")
    try:
        yanit = httpx.get(f"{adres}/api/tags", timeout=2)
        yanit.raise_for_status()
        return sorted(m["name"] for m in yanit.json().get("models", []))
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def model_olustur(tanim: str) -> DilModeli:
    """Büro ayarındaki tanımdan model nesnesi üretir: "ollama:qwen3.5:4b" gibi."""
    saglayici, _, model = tanim.partition(":")
    if saglayici == "ollama" and model:
        # 4K bağlam ve 5000 karakterlik parçalar ölçümde hız/doğruluk dengesini verdi
        return OllamaModeli(model, baglam=4096)
    raise ModelHatasi(f"Desteklenmeyen model tanımı: {tanim!r}")


class OllamaModeli:
    saglayici = "ollama"

    def __init__(self, model: str, adres: str | None = None, baglam: int = 8192, zaman_asimi: float = 600):
        self.model = model
        self.adres = adres or os.environ.get("OLLAMA_ADRESI", "http://127.0.0.1:11434")
        self.baglam = baglam
        self.zaman_asimi = zaman_asimi

    def json_tamamla(self, sistem: str, kullanici: str, sema: dict) -> dict:
        try:
            yanit = httpx.post(
                f"{self.adres}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": sistem}, {"role": "user", "content": kullanici}],
                    "format": sema,          # yapılandırılmış çıktı: yanıt bu şemaya uymak zorunda
                    "stream": False,
                    "think": False,          # bilgi çıkarmada uzun "düşünme" gerekmez, süreyi uzatır
                    "options": {"temperature": 0, "num_ctx": self.baglam},
                },
                timeout=self.zaman_asimi,
            )
            yanit.raise_for_status()
            icerik = yanit.json()["message"]["content"]
            return json.loads(icerik)
        except (httpx.HTTPError, KeyError, json.JSONDecodeError) as hata:
            raise ModelHatasi(f"{self.saglayici}/{self.model}: {type(hata).__name__}: {hata}") from hata
