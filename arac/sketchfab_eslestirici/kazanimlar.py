"""kazanimlar.csv okuma: sutun adlari ve kodlama esnek sekilde cozumlenir."""

from __future__ import annotations

import csv
import dataclasses
import io
import re
import unicodedata
from pathlib import Path

KODLAMALAR = ("utf-8-sig", "utf-8", "cp1254", "iso-8859-9", "latin-1")

# Normalize edilmis sutun adi -> mantiksal alan. Ilk eslesen kazanir.
SUTUN_IPUCLARI: dict[str, tuple[str, ...]] = {
    "seviye": ("seviye", "sinif", "duzey", "yas", "yasgrubu", "level", "grade"),
    "etkinlik": ("etkinlikadi", "etkinlik", "etkinlikismi", "activity", "activityname", "modul"),
    "kazanim": ("kazanim", "kazanimlar", "kazanimmetni", "outcome", "objective", "hedef",
                "ogrenmeciktilari", "ogrenmeciktilarivesurecbilesenleri"),
    # Baglam sutunlari (zorunlu degil): terim uretiminin isabetini artirir.
    "unite": ("unite", "ogrenmealani", "konu", "tema", "unit"),
    "icerik": ("etkinlikicerigi", "icerik", "aciklama", "content", "description"),
}


def _normalize(metin: str) -> str:
    """Turkce karakterleri ve bosluklari sadelestirip karsilastirilabilir yapar."""
    metin = metin.replace("İ", "i").replace("I", "i").replace("ı", "i")
    metin = unicodedata.normalize("NFKD", metin)
    metin = "".join(k for k in metin if not unicodedata.combining(k))
    return re.sub(r"[^a-z0-9]", "", metin.lower())


@dataclasses.dataclass(slots=True)
class Kazanim:
    sira: int
    seviye: str
    etkinlik: str
    kazanim: str
    unite: str = ""
    icerik: str = ""

    @property
    def kimlik(self) -> str:
        return f"K{self.sira:03d}"

    @property
    def baglam_imzasi(self) -> str:
        """Terim onbellegi anahtari: baglam degisirse terimler yeniden uretilir."""
        return " | ".join((self.kazanim, self.etkinlik, self.unite, self.icerik))


def _metni_coz(ham: bytes) -> str:
    for kodlama in KODLAMALAR:
        try:
            return ham.decode(kodlama)
        except UnicodeDecodeError:
            continue
    return ham.decode("utf-8", errors="replace")


def _ayirici_bul(ornek: str) -> str:
    try:
        return csv.Sniffer().sniff(ornek, delimiters=";,\t|").delimiter
    except csv.Error:
        # Excel'in Turkce yerel ayarinda noktali virgul yaygin.
        return ";" if ornek.count(";") > ornek.count(",") else ","


def _sutunlari_esle(basliklar: list[str]) -> dict[str, str]:
    esleme: dict[str, str] = {}
    normalize = {b: _normalize(b) for b in basliklar}
    for alan, ipuclari in SUTUN_IPUCLARI.items():
        # Once tam eslesme, sonra icerme.
        for baslik, norm in normalize.items():
            if baslik in esleme.values():
                continue
            if norm in ipuclari:
                esleme[alan] = baslik
                break
        else:
            for baslik, norm in normalize.items():
                if baslik in esleme.values():
                    continue
                if any(ipucu in norm for ipucu in ipuclari):
                    esleme[alan] = baslik
                    break
    return esleme


def oku(
    yol: Path,
    zorunlu_sutunlar: dict[str, str] | None = None,
) -> tuple[list[Kazanim], dict[str, str]]:
    """CSV'yi okur, (kazanim listesi, kullanilan sutun eslemesi) dondurur."""
    ham = Path(yol).read_bytes()
    metin = _metni_coz(ham)
    ilk_satirlar = "\n".join(metin.splitlines()[:5])
    ayirici = _ayirici_bul(ilk_satirlar)

    okuyucu = csv.DictReader(io.StringIO(metin), delimiter=ayirici)
    basliklar = [b for b in (okuyucu.fieldnames or []) if b is not None]
    if not basliklar:
        raise ValueError(f"{yol}: basliksiz veya bos CSV")

    esleme = _sutunlari_esle(basliklar)
    if zorunlu_sutunlar:
        esleme.update({k: v for k, v in zorunlu_sutunlar.items() if v})

    eksik = [a for a in ("etkinlik", "kazanim") if a not in esleme]
    if eksik:
        raise ValueError(
            f"{yol}: su sutunlar bulunamadi: {', '.join(eksik)}. "
            f"Dosyadaki basliklar: {', '.join(basliklar)}. "
            "--sutun-kazanim / --sutun-etkinlik / --sutun-seviye ile elle belirtebilirsiniz."
        )

    kazanimlar: list[Kazanim] = []
    for satir in okuyucu:
        metin_kazanim = (satir.get(esleme["kazanim"]) or "").strip()
        if not metin_kazanim:
            continue  # bos satirlari ve ara basliklari atla
        kazanimlar.append(
            Kazanim(
                sira=len(kazanimlar) + 1,
                seviye=(satir.get(esleme.get("seviye", "")) or "").strip(),
                etkinlik=(satir.get(esleme["etkinlik"]) or "").strip(),
                kazanim=metin_kazanim,
                unite=(satir.get(esleme.get("unite", "")) or "").strip(),
                icerik=(satir.get(esleme.get("icerik", "")) or "").strip(),
            )
        )
    return kazanimlar, esleme
