"""Kazanim metninden Ingilizce Sketchfab arama terimleri uretir.

Birincil yol: Anthropic Messages API (structured output ile dogrulanmis JSON).
Yedek yol: API anahtari yoksa / --llm-kapali verildiyse sozluk tabanli cikarim.
"""

from __future__ import annotations

import logging
import re
import unicodedata

import dataclasses
from typing import Any

from pydantic import BaseModel, Field

from .cache import Onbellek
from .kazanimlar import Kazanim

log = logging.getLogger(__name__)

SISTEM_TALIMATI = """\
Sen bir fen egitimi icerik kuratorusun. Turkce ilk/orta okul etkinliklerini
inceleyip, DERSTE 3B MODEL GOSTERMENIN GERCEKTEN ISE YARAYACAGI olanlari
seciyorsun ve yalnizca onlar icin Ingilizce Sketchfab arama terimi uretiyorsun.

Sana her satirda seviye, unite, ETKINLIK ADI, kazanim ve varsa etkinlik icerigi
verilir. DIKKAT: kazanim alani cogu zaman genel bir mufredat kodudur
("FAB.1. ... bilimsel gozlem yapabilme") ve konu hakkinda bilgi tasimaz. Boyle
durumlarda esas sinyal ETKINLIK ADI ve etkinlik icerigidir ("Lav Lambasi",
"Kopuren Dinozor" -> lava lamp, dinosaur). Satirin TAMAMINA bak.

ONCE KARAR VER: uygun = true mu?

uygun = true yalnizca su durumda: etkinligin merkezinde, 3B modeli dondurup
inceleyerek ogrenmeyi acikca kolaylastiran SOMUT bir nesne/yapi/organizma/olgu
var. Ornekler: iskelet, kalp, volkan, gunes sistemi, dinozor, hucre, basit
makine, elektrik devresi, periskop, mikroskop.

uygun = false ise terim URETME (terimler bos liste olsun) ve neden alanina kisa
bir Turkce gerekce yaz. Sunlar icin false ver:
- Sosyal-duygusal, degerler, iletisim, oz farkindalik temalari
  ("Duygularimi Kesfediyorum").
- El isi / karistirma / boyama sureci odakli etkinlikler; ogrenilen sey urun
  degil islemdir ("Mis Kokulu Kremim", "Bez Kalemlik Boyama").
- Soyut beceri veya surec kazanimlari (siniflandirma, tahmin, olcme) somut bir
  nesneye baglanmiyorsa.
- Kimyasal tepkime/renk degisimi gibi 3B statik modelin anlatamayacagi olaylar.

Karasiz kaldigin her durumda false ver. Az ama isabetli oneri, cok ama alakasiz
oneriden iyidir.

uygun = true ise 2-4 terim uret ve su kurallara uy:
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
- Seviyeyi dikkate al: okul oncesi icin basit ve tanidik nesneler, ust siniflar
  icin daha teknik modeller uygun.
"""


class TerimSeti(BaseModel):
    kimlik: str = Field(description="Kazanimin kimligi, girdideki ile birebir ayni")
    uygun: bool = Field(
        description="Bu etkinlik icin 3B model gostermek acikca ise yarar mi?"
    )
    terimler: list[str] = Field(
        default_factory=list,
        description="uygun=true ise 2-4 Ingilizce arama terimi, degilse bos liste",
    )
    neden: str = Field(
        default="", description="uygun=false ise kisa Turkce gerekce"
    )


class TerimYaniti(BaseModel):
    sonuclar: list[TerimSeti]


@dataclasses.dataclass(slots=True)
class TerimKarari:
    """Bir kazanim icin terim uretimi sonucu."""

    terimler: list[str] = dataclasses.field(default_factory=list)
    uygun: bool = True
    neden: str = ""

    @classmethod
    def sozlukten(cls, ham: Any) -> "TerimKarari":
        """Onbellekteki kayittan geri yukler (eski liste bicimini de kabul eder)."""
        if isinstance(ham, list):          # v1 onbellek bicimi
            return cls(terimler=list(ham), uygun=bool(ham))
        return cls(
            terimler=list(ham.get("terimler") or []),
            uygun=bool(ham.get("uygun", True)),
            neden=str(ham.get("neden") or ""),
        )

    def kayit(self) -> dict[str, Any]:
        return {"terimler": self.terimler, "uygun": self.uygun, "neden": self.neden}


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
    # Kesif Kutusu etkinlik adlarindan gelen ekler
    "lav lambasi": "lava lamp", "lav": "lava", "teraryum": "terrarium",
    "periskop": "periscope", "elektroskop": "electroscope", "terazi": "balance scale",
    "mum": "candle", "kalemlik": "pencil holder", "sabun": "soap bar",
    "balon": "balloon", "kavanoz": "glass jar", "galaksi": "galaxy",
    "ruzgar gulu": "pinwheel", "turbin": "wind turbine", "pusula": "compass",
    "mikroskop": "microscope", "buyutec": "magnifying glass", "huni": "funnel",
    "deney tupu": "test tube", "beher": "laboratory beaker", "pipet": "pipette",
    "maket": "scale model", "kopru": "bridge structure", "helikopter": "helicopter",
    "araba": "toy car", "ev": "house model", "bahce": "garden",
    "yagmur olcer": "rain gauge", "kar tanesi": "snowflake", "yanardag": "volcano",
    "kelebek": "butterfly", "kus yuvasi": "bird nest", "yumurta": "egg",
    "salyangoz": "snail", "orumcek": "spider", "ahtapot": "octopus",
    "penguen": "penguin", "kutup": "polar bear", "deve": "camel",
    "vucut": "human body", "el": "human hand", "ayak": "human foot",
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

    # Bilerek bos donulur: sozlukte karsiligi olmayan bir kazanim icin Turkce
    # kelimeleri terim diye gondermek Sketchfab'de alakasiz sonuc uretir.
    # Bos liste, kazanimin "Eslesmeyenler" olarak raporlanmasini saglar.
    return bulunan[:azami]


# --------------------------------------------------------------------------
# Birincil yol: Anthropic Messages API
# --------------------------------------------------------------------------


def _istemci():
    import anthropic

    return anthropic.Anthropic()


def _yigin_sor(istemci, model: str, yigin: list[Kazanim]) -> dict[str, TerimKarari]:
    satirlar = "\n".join(
        f"- kimlik: {k.kimlik}\n"
        f"  seviye: {k.seviye or '-'}\n"
        f"  unite: {k.unite or '-'}\n"
        f"  etkinlik: {k.etkinlik or '-'}\n"
        f"  kazanim: {k.kazanim}\n"
        f"  etkinlik_icerigi: {k.icerik or '-'}"
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
                    "Asagidaki etkinliklerin HER BIRI icin once uygun olup "
                    "olmadigina karar ver, uygunsa arama terimleri uret. "
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
    kararlar: dict[str, TerimKarari] = {}
    for sonuc in ayristirilmis.sonuclar:
        temiz = [t.strip() for t in sonuc.terimler if t and t.strip()][:4]
        # Model "uygun" deyip terim vermediyse uygunsuz sayilir: terimsiz arama yapilamaz.
        uygun = bool(sonuc.uygun and temiz)
        kararlar[sonuc.kimlik.strip()] = TerimKarari(
            terimler=temiz if uygun else [],
            uygun=uygun,
            neden=(sonuc.neden or "").strip() or ("" if uygun else "gerekçe belirtilmedi"),
        )
    return kararlar


def uret(
    kazanimlar: list[Kazanim],
    onbellek: Onbellek,
    model: str,
    yigin_boyu: int = 8,
    llm_kapali: bool = False,
    hepsini_dene: bool = False,
) -> dict[str, TerimKarari]:
    """Kazanim kimligi -> TerimKarari. Onbellekten okunur, eksikler uretilir."""
    sonuc: dict[str, TerimKarari] = {}
    eksik: list[Kazanim] = []

    for k in kazanimlar:
        anahtar = Onbellek.anahtar(
            "terimler", model if not llm_kapali else "sozluk", k.baglam_imzasi
        )
        onbellekten = onbellek.oku("terimler", anahtar)
        if onbellekten is not None:
            sonuc[k.kimlik] = TerimKarari.sozlukten(onbellekten)
        else:
            eksik.append(k)

    if not eksik:
        return sonuc

    if llm_kapali:
        for k in eksik:
            terimler = sozlukten_terimler(k.baglam_imzasi)
            karar = TerimKarari(
                terimler=terimler,
                uygun=bool(terimler),
                neden="" if terimler else "sözlükte somut bir nesne karşılığı bulunamadı",
            )
            sonuc[k.kimlik] = karar
            onbellek.yaz(
                "terimler",
                Onbellek.anahtar("terimler", "sozluk", k.baglam_imzasi),
                karar.kayit(),
                etiket=k.etkinlik[:80],
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
            karar = yanit.get(k.kimlik)
            if karar is None:
                # Yigindan yanit gelmediyse tek tek dene, o da olmazsa sozluge dus.
                try:
                    karar = _yigin_sor(istemci, model, [k]).get(k.kimlik)
                except Exception as hata:
                    log.warning("%s icin LLM basarisiz (%s); sozluge dusuluyor.",
                                k.kimlik, hata)
                if karar is None:
                    yedek = sozlukten_terimler(k.baglam_imzasi)
                    karar = TerimKarari(
                        terimler=yedek,
                        uygun=bool(yedek),
                        neden="" if yedek else "terim üretilemedi (LLM yanıtı alınamadı)",
                    )
            if hepsini_dene and not karar.uygun:
                # Uygunluk kapisini devre disi birak: sozlukten bir terim bulmayi dene.
                yedek = sozlukten_terimler(k.baglam_imzasi)
                if yedek:
                    karar = TerimKarari(terimler=yedek, uygun=True, neden="")
            sonuc[k.kimlik] = karar
            onbellek.yaz(
                "terimler",
                Onbellek.anahtar("terimler", model, k.baglam_imzasi),
                karar.kayit(),
                etiket=k.etkinlik[:80],
            )
    return sonuc
