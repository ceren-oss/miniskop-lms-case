"""Model puanlama: begeni + ucgen sayisi (tablet yuku) + gomulebilirlik."""

from __future__ import annotations

import math
import re

from .config import ACIK_LISANS_ANAHTARLARI, UCGEN_EGRISI, Ayarlar
from .sketchfab import Model

# Begeni puaninin doyuma ulastigi referans deger.
BEGENI_REFERANS = 1000

# Ilgi bonusunun ust siniri (puan 0-1 araliginda kalsin diye normalizasyonda kullanilir).
AZAMI_ILGI_BONUSU = 0.06


def begeni_puani(begeni: int) -> float:
    """Logaritmik olcek: 10 ile 100 begeni arasindaki fark, 900 ile 1000
    arasindakinden daha anlamlidir."""
    if begeni <= 0:
        return 0.0
    return min(1.0, math.log10(1 + begeni) / math.log10(1 + BEGENI_REFERANS))


def ucgen_puani(ucgen: int | None) -> float:
    """Tablette akiciligi temsil eder: kucuk model = yuksek puan."""
    if ucgen is None:
        return 0.5  # bilgi yok: ne odullendir ne cezalandir
    if ucgen <= 0:
        return 0.5
    noktalar = UCGEN_EGRISI
    if ucgen >= noktalar[-1][0]:
        return 0.0
    for (x0, y0), (x1, y1) in zip(noktalar, noktalar[1:]):
        if x0 <= ucgen <= x1:
            if x1 == x0:
                return y0
            oran = (ucgen - x0) / (x1 - x0)
            return y0 + (y1 - y0) * oran
    return 0.0


def lisans_puani(model: Model) -> float:
    """Lisans derste gomulup paylasilabilir mi?"""
    slug = (model.lisans_slug or "").lower()
    etiket = (model.lisans or "").lower()
    if slug and any(slug.startswith(a) for a in ACIK_LISANS_ANAHTARLARI):
        return 1.0
    # Slug beklenmedik bir bicimdeyse etiket metninden anlamaya calis.
    if "creative commons" in etiket or etiket.startswith("cc"):
        return 1.0
    if "standard" in etiket:
        return 0.9
    if not slug and not etiket:
        return 0.4  # lisans bilgisi yok: belirsiz
    return 0.2


def gomulebilirlik_puani(model: Model) -> float:
    """Embed edilebilirlik + ders ortamina uygunluk."""
    if not model.embed:
        return 0.0  # embed URL'i yoksa LMS'e gomulemez
    puan = 0.55 * lisans_puani(model)
    puan += 0.25                                   # embed URL'i var
    if model.animasyon > 0:
        puan += 0.10                               # animasyon anlatimi guclendirir
    if model.one_cikan:
        puan += 0.10                               # Sketchfab editor secimi
    return min(1.0, puan)


def _kelimeler(metin: str) -> set[str]:
    return {k for k in re.findall(r"[a-z]+", metin.lower()) if len(k) > 2}


def ilgi_bonusu(model: Model, terim: str) -> float:
    """Arama teriminin model adi/etiketlerinde gecmesi kucuk bir bonus verir.

    Filtre degil bonustur: Sketchfab'in kendi siralamasini ezmeden, konu disi
    ama populer modellerin en uste cikmasini zorlastirir.
    """
    hedef = _kelimeler(terim)
    if not hedef:
        return 0.0
    kaynak = _kelimeler(model.ad) | {e.lower() for e in model.etiketler}
    ortak = len(hedef & kaynak)
    return min(AZAMI_ILGI_BONUSU, 0.03 * ortak)


def puanla(model: Model, ayarlar: Ayarlar) -> Model:
    b = begeni_puani(model.begeni)
    u = ucgen_puani(model.ucgen)
    g = gomulebilirlik_puani(model)
    bonus = ilgi_bonusu(model, model.terim)

    agirlik_toplami = (
        ayarlar.agirlik_begeni + ayarlar.agirlik_ucgen + ayarlar.agirlik_gomulebilirlik
    ) or 1.0
    ham = (
        ayarlar.agirlik_begeni * b
        + ayarlar.agirlik_ucgen * u
        + ayarlar.agirlik_gomulebilirlik * g
    ) / agirlik_toplami
    # Ilgi bonusu siralamayi bozmadan 0-1 araliginda kalsin diye normalize edilir.
    model.puan = round((ham + bonus) / (1 + AZAMI_ILGI_BONUSU), 4)
    model.puan_detay = {
        "begeni": round(b, 3),
        "ucgen": round(u, 3),
        "gomulebilirlik": round(g, 3),
        "ilgi": round(bonus, 3),
    }
    return model


def elenmeli_mi(model: Model) -> str | None:
    """Ders ortamina hic uygun olmayanlari ele; sebebi dondur."""
    if model.yas_kisitli:
        return "yas kisitli"
    if not model.embed:
        return "embed URL'i yok"
    if not model.link:
        return "goruntuleyici linki yok"
    return None


def en_iyileri_sec(modeller: list[Model], ayarlar: Ayarlar) -> tuple[list[Model], dict[str, int]]:
    """Terimlerden gelen tum adaylari tekillestirir, puanlar ve ilk N'i dondurur."""
    elenen: dict[str, int] = {}
    tekil: dict[str, Model] = {}

    for model in modeller:
        sebep = elenmeli_mi(model)
        if sebep:
            elenen[sebep] = elenen.get(sebep, 0) + 1
            continue
        puanla(model, ayarlar)
        onceki = tekil.get(model.uid)
        # Ayni model birden fazla terimden gelebilir: en iyi puanlisini tut.
        if onceki is None or model.puan > onceki.puan:
            tekil[model.uid] = model

    siralanmis = sorted(tekil.values(), key=lambda m: (-m.puan, -m.begeni, m.ad))
    return siralanmis[: ayarlar.model_basina], elenen
