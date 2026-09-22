#!/usr/bin/env python3
"""Google Drive'daki "Keşif Kutusu ARGE" tablosundan kazanimlar.csv uretir.

Girdi: Drive MCP `read_file_content` ciktisi (JSON: {"fileContent": "<markdown>"}).
Tablo birden fazla sekmenin birlesimi oldugu icin once sutun sayisina gore
bloklara ayrilir, yalnizca "ÖĞRENME ÇIKTILARI" sutunu olan bloklar alinir.

Kullanim:
    python3 drive_kazanim_cikar.py <drive_ciktisi.json> -o kazanimlar.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

KAZANIM_BASLIGI = "ÖĞRENME ÇIKTILARI"
BASLIKLAR = ["Seviye", "Ünite", "Etkinlik", "Kazanım", "Etkinlik İçeriği"]

# "5\. SINIF" -> "5. SINIF" : Markdown kacislarini geri al
KACIS = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|])")

SEVIYE_DUZELTME = {
    "3 yas": "3 Yaş", "4 yas": "4 Yaş", "5-6 yas": "5-6 Yaş",
    "1 sinif": "1. Sınıf", "2 sinif": "2. Sınıf", "3 sinif": "3. Sınıf",
    "4 sinif": "4. Sınıf", "5 sinif": "5. Sınıf", "6 sinif": "6. Sınıf",
    "7 sinif": "7. Sınıf", "8 sinif": "8. Sınıf",
}


def _temizle(hucre: str) -> str:
    return re.sub(r"\s+", " ", KACIS.sub(r"\1", hucre)).strip()


def _seviye_normalize(ham: str) -> str:
    duz = ham.replace("İ", "i").replace("I", "i").replace("ı", "i").lower()
    duz = duz.replace("ş", "s").replace("ç", "c").replace("ğ", "g")
    duz = duz.replace("ö", "o").replace("ü", "u").replace("â", "a")
    anahtar = re.sub(r"[^a-z0-9]+", " ", duz).strip()
    anahtar = anahtar.replace("sinifi", "sinif").replace("yasi", "yas")
    anahtar = re.sub(r"\s+", " ", anahtar)
    # "5 6 yas" -> "5-6 yas"
    anahtar = re.sub(r"^(\d) (\d) yas$", r"\1-\2 yas", anahtar)
    return SEVIYE_DUZELTME.get(anahtar, ham)


def _satirlari_coz(metin: str) -> list[list[str]]:
    cozulmus = []
    for satir in metin.split("\n"):
        if not satir.lstrip().startswith("|"):
            continue
        hucreler = [_temizle(h) for h in satir.strip().strip("|").split("|")]
        cozulmus.append(hucreler)
    return cozulmus


def _bloklara_ayir(metin: str) -> list[list[list[str]]]:
    """Sutun sayisi degistiginde yeni sekme basladigini varsayar."""
    bloklar: list[list[list[str]]] = []
    mevcut: list[list[str]] = []
    onceki_genislik = None
    for satir in metin.split("\n"):
        if not satir.lstrip().startswith("|"):
            continue
        hucreler = [_temizle(h) for h in satir.strip().strip("|").split("|")]
        if len(hucreler) != onceki_genislik:
            if mevcut:
                bloklar.append(mevcut)
            mevcut, onceki_genislik = [], len(hucreler)
        mevcut.append(hucreler)
    if mevcut:
        bloklar.append(mevcut)
    return bloklar


def cikar(metin: str) -> list[dict[str, str]]:
    kayitlar: list[dict[str, str]] = []
    gorulen: set[tuple[str, str, str]] = set()

    for blok in _bloklara_ayir(metin):
        # Baslik satirini bul: kazanim sutunu iceren ilk satir
        baslik_indeksi = next(
            (i for i, s in enumerate(blok) if any(KAZANIM_BASLIGI in h.upper() for h in s)),
            None,
        )
        if baslik_indeksi is None:
            continue
        basliklar = blok[baslik_indeksi]
        kaz = next(i for i, h in enumerate(basliklar) if KAZANIM_BASLIGI in h.upper())
        etk = next((i for i, h in enumerate(basliklar) if h.upper().startswith("ETKİNLİK")
                    and i != kaz), kaz - 1)
        uni = next((i for i, h in enumerate(basliklar) if h.upper().startswith("ÜNİTE")), None)
        ice = next((i for i, h in enumerate(basliklar)
                    if "İÇERİĞİ" in h.upper()), None)

        # Seviye sutunu tabloda birlestirilmis hucre oldugu icin yalnizca grubun
        # ilk satirinda dolu; sonraki satirlara ileri-doldurma ile tasinir.
        son_seviye = ""
        for satir in blok[baslik_indeksi + 1:]:
            def al(i: int | None) -> str:
                return satir[i] if i is not None and i < len(satir) else ""

            if satir and satir[0]:
                son_seviye = _seviye_normalize(satir[0])

            kazanim, etkinlik = al(kaz), al(etk)
            if not kazanim or not etkinlik:
                continue
            if KAZANIM_BASLIGI in kazanim.upper():   # tekrar eden baslik satiri
                continue
            seviye = son_seviye
            imza = (seviye.lower(), etkinlik.lower(), kazanim.lower())
            if imza in gorulen:
                continue
            gorulen.add(imza)
            kayitlar.append({
                "Seviye": seviye,
                "Ünite": al(uni),
                "Etkinlik": etkinlik,
                "Kazanım": kazanim,
                "Etkinlik İçeriği": al(ice),
            })
    return kayitlar


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("girdi", type=Path, help="Drive read_file_content JSON çıktısı")
    a.add_argument("-o", "--cikti", type=Path, default=Path("kazanimlar.csv"))
    args = a.parse_args()

    govde = json.loads(args.girdi.read_text(encoding="utf-8"))
    metin = govde["fileContent"] if isinstance(govde, dict) else str(govde)
    kayitlar = cikar(metin)
    if not kayitlar:
        print("Kazanım bulunamadı.", file=sys.stderr)
        return 1

    with args.cikti.open("w", encoding="utf-8-sig", newline="") as f:
        yazici = csv.DictWriter(f, fieldnames=BASLIKLAR, delimiter=";")
        yazici.writeheader()
        yazici.writerows(kayitlar)

    seviyeler: dict[str, int] = {}
    for k in kayitlar:
        seviyeler[k["Seviye"]] = seviyeler.get(k["Seviye"], 0) + 1
    print(f"{len(kayitlar)} kazanım -> {args.cikti}")
    for s, n in sorted(seviyeler.items()):
        print(f"  {n:4d}  {s or '(seviye yok)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
