"""Sabitler ve calisma ayarlari."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

SKETCHFAB_API = "https://api.sketchfab.com/v3"

# Sketchfab search endpoint'i sayfa basina en fazla 24 sonuc dondurur.
ARAMA_SAYFA_LIMITI = 24

VARSAYILAN_MODEL = "claude-opus-5"

# Tabletlerde akici calismasi beklenen model buyuklukleri (ucgen/yuz sayisi).
# (esik, puan) kirilim noktalari; aradaki degerler dogrusal interpolasyonla bulunur.
UCGEN_EGRISI: tuple[tuple[int, float], ...] = (
    (0, 1.00),
    (50_000, 1.00),
    (150_000, 0.80),
    (500_000, 0.40),
    (1_500_000, 0.00),
)

# Cocuklara acik, derslerde gomulebilir kabul ettigimiz lisans slug'lari.
# Sketchfab'in lisans slug'lari surume gore degisebildigi icin etiket metni
# uzerinden de bir yedek kontrol yapilir (bkz. puanlama.lisans_puani).
ACIK_LISANS_ANAHTARLARI = (
    "cc0",
    "cc-by",
    "cc-by-sa",
    "cc-by-nd",
    "cc-by-nc",
    "cc-by-nc-sa",
    "cc-by-nc-nd",
    "st",  # Sketchfab Standard
    "sketchfab-standard",
    "free-standard",
)


@dataclasses.dataclass(slots=True)
class Ayarlar:
    """Tek bir calistirmanin tum ayarlari."""

    girdi: Path
    cikti_dizini: Path
    onbellek_dizini: Path
    xlsx_adi: str = "eslesmeler.xlsx"
    html_adi: str = "onizleme.html"

    limit: int | None = None          # kac kazanim islenecek (test icin)
    model_basina: int = 5             # kazanim basina secilecek model sayisi
    aday_sayisi: int = ARAMA_SAYFA_LIMITI  # her terim icin cekilecek aday sayisi

    # Anthropic
    llm_model: str = VARSAYILAN_MODEL
    llm_yigin: int = 8                # tek istekte kac kazanim
    llm_kapali: bool = False          # True ise sozluk tabanli yedek kullanilir

    # Sketchfab
    sketchfab_token: str | None = None
    bekleme: float = 1.0              # istekler arasi en az bekleme (saniye)
    azami_deneme: int = 5
    max_ucgen: int | None = None      # API tarafinda max_face_count filtresi
    sahte_veri: bool = False          # ag erisimi olmadan calistirma (demo)

    # Puanlama agirliklari
    agirlik_begeni: float = 0.45
    agirlik_ucgen: float = 0.35
    agirlik_gomulebilirlik: float = 0.20

    kati_sema: bool = False           # alan adi uyusmazliginda calismayi durdur
    onbellek_omru_gun: float | None = None

    # Otomatik algilama yetmediginde elle verilen sutun eslemesi
    sutun_eslemesi: dict[str, str] | None = None

    @property
    def xlsx_yolu(self) -> Path:
        return self.cikti_dizini / self.xlsx_adi

    @property
    def html_yolu(self) -> Path:
        return self.cikti_dizini / self.html_adi


def ortamdan_token() -> str | None:
    """Sketchfab token'i ortam degiskeninden okur (istege bagli)."""
    for anahtar in ("SKETCHFAB_API_TOKEN", "SKETCHFAB_TOKEN"):
        deger = os.environ.get(anahtar)
        if deger:
            return deger.strip()
    return None
