"""Kazanim metninden Ingilizce Sketchfab arama terimleri uretir.

Birincil yol: Anthropic Messages API (structured output ile dogrulanmis JSON).
Yedek yol: API anahtari yoksa / --llm-kapali verildiyse sozluk tabanli cikarim.
"""

from __future__ import annotations

import logging
import re
import unicodedata

from pydantic import BaseModel, Field

from .cache import Onbellek
from .kazanimlar import Kazanim

log = logging.getLogger(__name__)

SISTEM_TALIMATI = """\
Sen bir fen egitimi icerik kuratorusun. Turkce ilk/orta okul kazanimlarini,
Sketchfab'de 3B model aramak icin kullanilacak INGILIZCE arama terimlerine
ceviriyorsun.

Her kazanim icin 2-4 terim uret ve su kurallara uy:
- Terimler INGILIZCE olacak.
- Her terim 1-3 kelime, tekil, somut bir NESNE/YAPI/OLGU adi olacak
  ("volcano", "human heart", "solar system"). 3B model olarak var olabilecek
  seyleri yaz.
- Soyut kaliplardan kacin: "understanding", "importance of", "activity",
  "lesson", "for kids", "education" gibi kelimeler kullanma.
- Bilimsel olarak dogru ve cocuk seviyesine uygun ol; korkutucu veya
  yas kisitli icerige yonlendirecek terimler yazma (orn. "corpse", "weapon").
- Terimler birbirinden farkli acilari yakalasin; ayni seyin es anlamlisini
  tekrar yazma.
- Kazanim birden fazla kavram iceriyorsa en gorsellestirilebilir olanlari sec.
"""


class TerimSeti(BaseModel):
    kimlik: str = Field(description="Kazanimin kimligi, girdideki ile birebir ayni")
    terimler: list[str] = Field(description="2-4 adet Ingilizce arama terimi")


class TerimYaniti(BaseModel):
    sonuclar: list[TerimSeti]


# --------------------------------------------------------------------------
# Yedek yol: sozluk tabanli terim cikarimi (LLM yokken calisir)
# --------------------------------------------------------------------------

SOZLUK: dict[str, str] = {
    # gok bilimi
    "gunes sistemi": "solar system", "gunes": "sun", "ay": "moon",
    "dunya": "planet earth", "gezegen": "planet", "yildiz": "star",
    "uydu": "satellite", "uzay": "space station", "teleskop": "telescope",
    "roket": "rocket", "astronot": "astronaut", "meteor": "meteorite",
    "kuyruklu yildiz": "comet", "galaksi": "galaxy", "ay evreleri": "moon phases",
    # canlilar
    "hucre": "animal cell", "bitki hucresi": "plant cell", "bakteri": "bacteria",
    "virus": "virus", "dna": "dna molecule", "iskelet": "human skeleton",
    "kemik": "bone", "kas": "human muscle", "kalp": "human heart",
    "akciger": "human lungs", "beyin": "human brain", "goz": "human eye",
    "kulak": "human ear", "dis": "human tooth", "mide": "stomach anatomy",
    "sindirim": "digestive system", "dolasim": "circulatory system",
    "solunum": "respiratory system", "bobrek": "kidney anatomy",
    "bitki": "plant", "yaprak": "leaf", "cicek": "flower anatomy",
    "tohum": "seed", "kok": "plant roots", "agac": "tree",
    "mantar": "mushroom", "yosun": "moss", "hayvan": "animal",
    "kus": "bird", "balik": "fish", "bocek": "insect", "kelebek": "butterfly",
    "ari": "honey bee", "karinca": "ant", "kurbaga": "frog", "yilan": "snake",
    "kaplumbaga": "turtle", "dinozor": "dinosaur", "fosil": "fossil",
    "besin zinciri": "food chain", "ekosistem": "ecosystem",
    # madde ve fizik
    "atom": "atom model", "molekul": "molecule", "element": "periodic table",
    "periyodik": "periodic table", "kristal": "crystal structure",
    "miknatis": "magnet", "manyetik": "magnetic field", "elektrik": "electric circuit",
    "devre": "electric circuit", "pil": "battery", "ampul": "light bulb",
    "isik": "light prism", "mercek": "optical lens", "ayna": "mirror optics",
    "ses": "sound wave", "dalga": "wave physics", "kuvvet": "lever mechanism",
    "hareket": "pendulum", "surtunme": "inclined plane", "yercekimi": "gravity model",
    "basit makine": "simple machine", "kaldirac": "lever", "makara": "pulley",
    "egik duzlem": "inclined plane", "disli": "gear mechanism",
    "kaldirma kuvveti": "buoyancy", "basinc": "hydraulic press",
    "termometre": "thermometer", "sicaklik": "thermometer", "isi": "heat engine",
    "enerji": "wind turbine", "elektrik uretimi": "power plant",
    "gunes paneli": "solar panel", "ruzgar": "wind turbine",
    "buhar": "steam engine", "motor": "engine",
    # yer bilimi
    "volkan": "volcano", "deprem": "tectonic plates", "levha": "tectonic plates",
    "kaya": "rock formation", "mineral": "mineral crystal", "toprak": "soil layers",
    "su dongusu": "water cycle", "bulut": "cloud formation", "yagmur": "rain cloud",
    "hava": "weather station", "iklim": "climate globe", "buzul": "glacier",
    "magara": "cave", "dag": "mountain terrain", "nehir": "river landscape",
    "okyanus": "ocean floor", "mercan": "coral reef", "cop": "recycling bin",
    "geri donusum": "recycling bin", "kirlilik": "plastic waste",
    # teknoloji / tasarim
    "robot": "robot", "makine": "machine", "kopru": "bridge structure",
    "bina": "building structure", "arac": "vehicle", "ucak": "airplane",
    "gemi": "ship", "tren": "train", "pusula": "compass",
    "saat": "mechanical clock", "carki": "gear mechanism",
}

DURAK_KELIMELER = {
    "ve", "ile", "icin", "bir", "bu", "olan", "gibi", "kendi", "uzerinde",
    "arasinda", "ogrenci", "ogrenciler", "ogrenir", "kavrar", "aciklar",
    "fark", "eder", "yapar", "tasarlar", "gozlemler", "gozlemleyerek",
    "model", "modeli", "ornek", "verir", "kullanarak", "olusturur",
    "inceleyerek", "siniflandirir", "tanir", "bilir", "anlatir",
}


def _sadelestir(metin: str) -> str:
    metin = metin.replace("İ", "i").replace("I", "i").replace("ı", "i")
    metin = unicodedata.normalize("NFKD", metin)
    metin = "".join(k for k in metin if not unicodedata.combining(k))
    return metin.lower()


def _anahtar_deseni(anahtar: str) -> re.Pattern[str]:
    """Sozluk anahtari icin kelime basina bagli desen.

    Turkce eklemeli bir dil oldugu icin sonek serbest birakilir ("volkan" ->
    "volkanik"), ama kelime ORTASINDA eslesmeye izin verilmez: aksi halde
    "olusumlari" icindeki "ari" bal arisi sanilir. Cok kisa anahtarlarda
    ("ay", "su") sonek de serbest birakilmaz, cunku yanlis pozitif riski yuksek.
    """
    govde = re.escape(anahtar)
    son = r"(?![a-z0-9])" if len(anahtar) <= 3 else ""
    return re.compile(rf"(?<![a-z0-9]){govde}{son}")


_DESEN_ONBELLEGI: dict[str, re.Pattern[str]] = {}


def sozlukten_terimler(kazanim: str, azami: int = 4) -> list[str]:
    """LLM yokken kullanilan basit ama deterministik cikarim."""
    duz = _sadelestir(kazanim)
    bulunan: list[str] = []

    # Once cok kelimeli anahtarlar (daha spesifik olduklari icin).
    for anahtar in sorted(SOZLUK, key=lambda a: -len(a)):
        desen = _DESEN_ONBELLEGI.setdefault(anahtar, _anahtar_deseni(anahtar))
        if desen.search(duz):
            terim = SOZLUK[anahtar]
            if terim not in bulunan:
                bulunan.append(terim)
        if len(bulunan) >= azami:
            break

    if not bulunan:
        # Hicbir sey eslesmediyse en uzun icerikli kelimeleri terim yap.
        kelimeler = [
            k for k in re.findall(r"[a-z]+", duz)
            if len(k) > 4 and k not in DURAK_KELIMELER
        ]
        bulunan = sorted(set(kelimeler), key=len, reverse=True)[:2]
    return bulunan[:azami]


# --------------------------------------------------------------------------
# Birincil yol: Anthropic Messages API
# --------------------------------------------------------------------------


def _istemci():
    import anthropic

    return anthropic.Anthropic()


def _yigin_sor(istemci, model: str, yigin: list[Kazanim]) -> dict[str, list[str]]:
    satirlar = "\n".join(
        f"- kimlik: {k.kimlik}\n"
        f"  seviye: {k.seviye or '-'}\n"
        f"  etkinlik: {k.etkinlik or '-'}\n"
        f"  kazanim: {k.kazanim}"
        for k in yigin
    )
    yanit = istemci.messages.parse(
        model=model,
        max_tokens=4000,
        system=SISTEM_TALIMATI,
        messages=[
            {
                "role": "user",
                "content": (
                    "Asagidaki kazanimlarin HER BIRI icin arama terimleri uret. "
                    "Cikti listesi girdideki kimliklerin tamamini icermeli.\n\n"
                    f"{satirlar}"
                ),
            }
        ],
        output_format=TerimYaniti,
    )
    ayristirilmis = yanit.parsed_output
    if ayristirilmis is None:
        return {}
    return {
        s.kimlik.strip(): [t.strip() for t in s.terimler if t and t.strip()]
        for s in ayristirilmis.sonuclar
    }


def uret(
    kazanimlar: list[Kazanim],
    onbellek: Onbellek,
    model: str,
    yigin_boyu: int = 8,
    llm_kapali: bool = False,
) -> dict[str, list[str]]:
    """Kazanim kimligi -> terim listesi. Onbellekten okunur, eksikler uretilir."""
    sonuc: dict[str, list[str]] = {}
    eksik: list[Kazanim] = []

    for k in kazanimlar:
        anahtar = Onbellek.anahtar("terimler", model if not llm_kapali else "sozluk", k.kazanim)
        onbellekten = onbellek.oku("terimler", anahtar)
        if onbellekten:
            sonuc[k.kimlik] = onbellekten
        else:
            eksik.append(k)

    if not eksik:
        return sonuc

    if llm_kapali:
        for k in eksik:
            terimler = sozlukten_terimler(k.kazanim)
            sonuc[k.kimlik] = terimler
            onbellek.yaz(
                "terimler",
                Onbellek.anahtar("terimler", "sozluk", k.kazanim),
                terimler,
                etiket=k.kazanim[:80],
            )
        return sonuc

    istemci = _istemci()
    for bas in range(0, len(eksik), yigin_boyu):
        yigin = eksik[bas : bas + yigin_boyu]
        try:
            yanit = _yigin_sor(istemci, model, yigin)
        except Exception as hata:  # ag/kota/dogrulama - yigini tek tek dene
            log.warning("Yigin istegi basarisiz (%s); tek tek denenecek.", hata)
            yanit = {}

        for k in yigin:
            terimler = yanit.get(k.kimlik) or []
            if not terimler:
                try:
                    tek = _yigin_sor(istemci, model, [k])
                    terimler = tek.get(k.kimlik) or []
                except Exception as hata:
                    log.warning("K%s icin LLM basarisiz (%s); sozluge dusuluyor.", k.kimlik, hata)
            if not terimler:
                terimler = sozlukten_terimler(k.kazanim)
            terimler = terimler[:4]
            sonuc[k.kimlik] = terimler
            onbellek.yaz(
                "terimler",
                Onbellek.anahtar("terimler", model, k.kazanim),
                terimler,
                etiket=k.kazanim[:80],
            )
    return sonuc
