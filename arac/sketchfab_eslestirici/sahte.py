"""Ag erisimi olmadan calistirma icin ORNEK (sahte) Sketchfab yanitlari.

Bu modul yalnizca boru hattini ucdan uca denemek icindir. Urettigi kayitlar
gercek Sketchfab modelleri DEGILDIR; her model adi "ORNEK VERI" ile baslar ve
--sahte-veri ile uretilen ciktilarin basina uyari serilir.

Yanit govdesi bilerek gercek API'nin alan adlariyla ayni kurgudadir; boylece
sema cozumleme ve cevirme kodu da bu modda test edilmis olur.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any

from .cache import Onbellek
from .sketchfab import SketchfabIstemcisi

ORNEK_YAZARLAR = (
    ("ornek-atolye", "Örnek Atölye"),
    ("demo-3d", "Demo 3D"),
    ("ornek-muze", "Örnek Müze"),
    ("okul-lab", "Okul Lab"),
)

ORNEK_LISANSLAR = (
    ("cc-by", "CC Attribution"),
    ("cc-by-sa", "CC Attribution-ShareAlike"),
    ("cc0", "CC0 Public Domain"),
    ("st", "Sketchfab Standard"),
    ("cc-by-nc", "CC Attribution-NonCommercial"),
)

_SVG = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='448' height='252'>"
    "<rect width='100%25' height='100%25' fill='%23dde3ea'/>"
    "<text x='50%25' y='48%25' font-family='sans-serif' font-size='20' "
    "fill='%23566' text-anchor='middle'>ÖRNEK ÖNİZLEME</text>"
    "<text x='50%25' y='68%25' font-family='sans-serif' font-size='14' "
    "fill='%23889' text-anchor='middle'>{terim}</text></svg>"
)


def _tohum(terim: str) -> int:
    return int(hashlib.sha256(terim.encode("utf-8")).hexdigest()[:8], 16)


def sahte_yanit(terim: str, sayi: int) -> dict[str, Any]:
    """Gercek /v3/search govdesiyle ayni bicimde ornek yanit uretir."""
    rastgele = random.Random(_tohum(terim))
    sonuclar = []
    for i in range(sayi):
        uid = f"ornek{_tohum(terim):08x}{i:02d}"
        yazar_kod, yazar_ad = ORNEK_YAZARLAR[i % len(ORNEK_YAZARLAR)]
        lisans_slug, lisans_ad = ORNEK_LISANSLAR[i % len(ORNEK_LISANSLAR)]
        # Begeni sirasi: sort_by=-likeCount davranisini taklit et.
        begeni = max(1, int(rastgele.uniform(80, 2400) * (0.88 ** i)))
        sonuclar.append(
            {
                "uid": uid,
                "name": f"ÖRNEK VERİ – {terim.title()} {i + 1}",
                "viewerUrl": f"https://sketchfab.com/search?q={terim.replace(' ', '+')}&type=models",
                "embedUrl": f"https://sketchfab.com/models/{uid}/embed",
                "likeCount": begeni,
                "viewCount": begeni * rastgele.randint(8, 60),
                "faceCount": rastgele.choice(
                    [rastgele.randint(4_000, 90_000), rastgele.randint(90_000, 400_000),
                     rastgele.randint(400_000, 2_000_000)]
                ),
                "vertexCount": rastgele.randint(3_000, 900_000),
                "animationCount": rastgele.choice([0, 0, 0, 1, 2]),
                "isAgeRestricted": False,
                "isDownloadable": rastgele.choice([True, False]),
                "staffpickedAt": "2024-05-01T10:00:00.000000" if i % 7 == 0 else None,
                "publishedAt": "2024-01-01T10:00:00.000000",
                "tags": [{"name": k} for k in terim.split()] + [{"name": "science"}],
                "categories": [{"name": "science-technology"}],
                "thumbnails": {
                    "images": [
                        {"url": _SVG.format(terim=terim.replace(" ", "+")), "width": 448, "height": 252},
                        {"url": _SVG.format(terim=terim.replace(" ", "+")), "width": 128, "height": 72},
                    ]
                },
                "user": {
                    "username": yazar_kod,
                    "displayName": yazar_ad,
                    "profileUrl": f"https://sketchfab.com/{yazar_kod}",
                },
                "license": {"slug": lisans_slug, "label": lisans_ad},
            }
        )
    return {"results": sonuclar, "next": None, "previous": None}


class SahteIstemci(SketchfabIstemcisi):
    """Gercek istemcinin ag katmanini ornek yanitla degistirir."""

    def __init__(self, onbellek: Onbellek, **kwargs: Any) -> None:
        super().__init__(onbellek, bekleme=0.0, **kwargs)

    def _ag_istegi(self, yol: str, parametreler: dict[str, Any]) -> dict[str, Any]:
        # Yalnizca ag katmani degisir: onbellek, sema cozumleme ve cevirme
        # gercek kod yolundan gecer.
        self.istek_sayisi += 1
        return sahte_yanit(str(parametreler.get("q", "")), int(parametreler.get("count", 24)))
