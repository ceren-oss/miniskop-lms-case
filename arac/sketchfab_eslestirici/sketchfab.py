"""Sketchfab Data API v3 istemcisi.

Alan adlari TAHMIN EDILMEZ: her mantiksal alan icin aday API alan adlari
tanimlanir, ilk basarili yanitta gercek govdeye karsi cozumlenir ve cozulemeyen
alanlar acikca raporlanir (--kati-sema ile calisma durdurulur). `--sema-incele`
komutu ham bir sonucu diske yazar; boylece tam calistirmadan once alan adlari
gozle dogrulanabilir.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import random
import time
from typing import Any, Iterable

import requests

from .cache import Onbellek
from .config import ARAMA_SAYFA_LIMITI, SKETCHFAB_API

log = logging.getLogger(__name__)

# mantiksal alan -> yanitta aranacak aday alan adlari (oncelik sirasiyla)
ALAN_ADAYLARI: dict[str, tuple[str, ...]] = {
    "uid": ("uid", "id"),
    "ad": ("name", "title"),
    "link": ("viewerUrl", "viewer_url", "url"),
    "embed": ("embedUrl", "embed_url"),
    "begeni": ("likeCount", "like_count", "likes"),
    "goruntulenme": ("viewCount", "view_count", "views"),
    "ucgen": ("faceCount", "face_count", "triangleCount", "triangles"),
    "koordinat": ("vertexCount", "vertex_count", "vertices"),
    "animasyon": ("animationCount", "animation_count"),
    "yas_kisitli": ("isAgeRestricted", "is_age_restricted"),
    "indirilebilir": ("isDownloadable", "is_downloadable"),
    "one_cikan": ("staffpickedAt", "staffpicked_at", "isStaffpicked"),
    "yayin_tarihi": ("publishedAt", "published_at", "createdAt"),
    "etiketler": ("tags",),
    "kategoriler": ("categories",),
    "kucuk_gorsel": ("thumbnails",),
    "yazar": ("user", "owner"),
    "lisans": ("license",),
}

# Bunlar olmadan bir model listelenemez; eksikse sema uyari verir.
ZORUNLU_ALANLAR = ("uid", "ad", "link", "begeni")

UST_DUZEY_ADAYLAR = {
    "sonuclar": ("results",),
    "sonraki": ("next", "cursors"),
}


class SemaUyusmazligi(RuntimeError):
    pass


@dataclasses.dataclass(slots=True)
class Model:
    """Sketchfab sonucunun araca ozgu, sadelestirilmis gorunumu."""

    uid: str
    ad: str
    link: str
    embed: str
    yazar_ad: str
    yazar_link: str
    begeni: int
    goruntulenme: int
    ucgen: int | None
    animasyon: int
    lisans: str
    lisans_slug: str
    kucuk_gorsel: str
    yas_kisitli: bool
    one_cikan: bool
    etiketler: list[str]
    terim: str = ""       # bu modeli bulan arama terimi
    puan: float = 0.0
    puan_detay: dict[str, float] = dataclasses.field(default_factory=dict)

    def sozluk(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _ilk_var_olan(govde: dict[str, Any], adaylar: Iterable[str]) -> tuple[str | None, Any]:
    for aday in adaylar:
        if aday in govde:
            return aday, govde[aday]
    return None, None


class SemaRaporu:
    def __init__(self) -> None:
        self.cozulen: dict[str, str] = {}
        self.cozulemeyen: list[str] = []
        self.beklenmeyen: list[str] = []

    def metin(self) -> str:
        satirlar = ["Sketchfab alan semasi (canli yanittan dogrulandi):"]
        for mantiksal, gercek in sorted(self.cozulen.items()):
            satirlar.append(f"  ✓ {mantiksal:<14} -> {gercek}")
        for mantiksal in self.cozulemeyen:
            satirlar.append(f"  ✗ {mantiksal:<14} -> BULUNAMADI (adaylar: {', '.join(ALAN_ADAYLARI[mantiksal])})")
        if self.beklenmeyen:
            satirlar.append(f"  · yanitta olup kullanilmayan alanlar: {', '.join(sorted(self.beklenmeyen))}")
        return "\n".join(satirlar)

    @property
    def saglikli(self) -> bool:
        return not any(a in self.cozulemeyen for a in ZORUNLU_ALANLAR)


class SketchfabIstemcisi:
    def __init__(
        self,
        onbellek: Onbellek,
        token: str | None = None,
        bekleme: float = 1.0,
        azami_deneme: int = 5,
        kati_sema: bool = False,
    ) -> None:
        self.onbellek = onbellek
        self.bekleme = bekleme
        self.azami_deneme = azami_deneme
        self.kati_sema = kati_sema
        self.oturum = requests.Session()
        self.oturum.headers["User-Agent"] = "kesif-kutusu-model-eslestirici/1.0"
        if token:
            # Data API v3 kimlik dogrulamasi: "Authorization: Token <token>"
            self.oturum.headers["Authorization"] = f"Token {token}"
        self._son_istek = 0.0
        self.sema: SemaRaporu | None = None
        self.istek_sayisi = 0

    # ---------------------------------------------------------------- HTTP

    def _hiz_sinirla(self) -> None:
        gecen = time.monotonic() - self._son_istek
        kalan = self.bekleme - gecen
        if kalan > 0:
            time.sleep(kalan + random.uniform(0, 0.15))  # jitter: es zamanli dalga olmasin
        self._son_istek = time.monotonic()

    def _istek(self, yol: str, parametreler: dict[str, Any]) -> dict[str, Any]:
        """Onbellekli, hiz sinirli, geri cekilmeli GET."""
        anahtar = Onbellek.anahtar(yol, parametreler)
        onbellekten = self.onbellek.oku("sketchfab", anahtar)
        if onbellekten is not None:
            return onbellekten

        govde = self._ag_istegi(yol, parametreler)
        self.onbellek.yaz("sketchfab", anahtar, govde, etiket=str(parametreler.get("q", yol)))
        return govde

    def _ag_istegi(self, yol: str, parametreler: dict[str, Any]) -> dict[str, Any]:
        """Hiz sinirli, geri cekilmeli ham HTTP cagrisi (onbelleksiz)."""
        url = f"{SKETCHFAB_API}{yol}"
        son_hata: Exception | None = None

        for deneme in range(1, self.azami_deneme + 1):
            self._hiz_sinirla()
            try:
                yanit = self.oturum.get(url, params=parametreler, timeout=30)
                self.istek_sayisi += 1
            except requests.RequestException as hata:
                son_hata = hata
                bekle = min(2 ** deneme, 30)
                log.warning("Ag hatasi (%s); %.0fs sonra tekrar (%d/%d)", hata, bekle, deneme, self.azami_deneme)
                time.sleep(bekle)
                continue

            if yanit.status_code == 429:
                # Sunucu soyluyorsa ona uy, yoksa ustel geri cekil.
                basliktan = yanit.headers.get("Retry-After")
                bekle = float(basliktan) if basliktan and basliktan.isdigit() else min(2 ** deneme, 60)
                log.warning("Hiz siniri (429); %.0fs bekleniyor (%d/%d)", bekle, deneme, self.azami_deneme)
                time.sleep(bekle)
                continue

            if 500 <= yanit.status_code < 600:
                bekle = min(2 ** deneme, 30)
                log.warning("Sunucu hatasi %s; %.0fs sonra tekrar", yanit.status_code, bekle)
                time.sleep(bekle)
                continue

            if yanit.status_code == 400:
                # Genelde desteklenmeyen bir filtre parametresi. Cagiran taraf
                # parametreyi dusurup tekrar deneyebilsin diye ayirt edilebilir hata.
                raise ValueError(f"400 Bad Request: {yanit.text[:300]}")

            yanit.raise_for_status()
            return yanit.json()

        raise RuntimeError(f"{url} icin {self.azami_deneme} deneme basarisiz: {son_hata}")

    # ---------------------------------------------------------------- sema

    def _semayi_dogrula(self, govde: dict[str, Any]) -> SemaRaporu:
        rapor = SemaRaporu()
        ad, sonuclar = _ilk_var_olan(govde, UST_DUZEY_ADAYLAR["sonuclar"])
        if ad is None or not isinstance(sonuclar, list):
            raise SemaUyusmazligi(
                "Yanitta 'results' listesi yok. Ust duzey anahtarlar: "
                + ", ".join(sorted(govde))
            )
        if not sonuclar:
            return rapor  # bos sonuc: dogrulanacak alan yok

        ornek = sonuclar[0]
        kullanilan: set[str] = set()
        for mantiksal, adaylar in ALAN_ADAYLARI.items():
            gercek, _ = _ilk_var_olan(ornek, adaylar)
            if gercek is None:
                rapor.cozulemeyen.append(mantiksal)
            else:
                rapor.cozulen[mantiksal] = gercek
                kullanilan.add(gercek)
        rapor.beklenmeyen = [a for a in ornek if a not in kullanilan]
        return rapor

    def _semayi_kur(self, govde: dict[str, Any]) -> None:
        if self.sema is not None:
            return
        rapor = self._semayi_dogrula(govde)
        if not rapor.cozulen and not rapor.cozulemeyen:
            return  # bos ilk yanit: bir sonrakinde tekrar dene
        self.sema = rapor
        log.info("%s", rapor.metin())
        if not rapor.saglikli:
            mesaj = (
                "Sketchfab yanitinda zorunlu alanlar bulunamadi; API semasi degismis olabilir.\n"
                + rapor.metin()
            )
            if self.kati_sema:
                raise SemaUyusmazligi(mesaj)
            log.warning("%s", mesaj)

    def _al(self, ham: dict[str, Any], mantiksal: str, varsayilan: Any = None) -> Any:
        """Cozumlenmis sema uzerinden bir alani guvenle okur."""
        if self.sema and mantiksal in self.sema.cozulen:
            return ham.get(self.sema.cozulen[mantiksal], varsayilan)
        _, deger = _ilk_var_olan(ham, ALAN_ADAYLARI.get(mantiksal, ()))
        return varsayilan if deger is None else deger

    # -------------------------------------------------------------- arama

    def ara(
        self,
        terim: str,
        sayi: int = ARAMA_SAYFA_LIMITI,
        max_ucgen: int | None = None,
    ) -> list[Model]:
        parametreler: dict[str, Any] = {
            "type": "models",
            "q": terim,
            "sort_by": "-likeCount",   # en cok begenilen once
            "count": min(sayi, ARAMA_SAYFA_LIMITI),
        }
        if max_ucgen:
            parametreler["max_face_count"] = max_ucgen

        try:
            govde = self._istek("/search", parametreler)
        except ValueError as hata:
            # Istege bagli filtre desteklenmiyorsa onsuz tekrar dene.
            if max_ucgen and "400" in str(hata):
                log.warning("max_face_count filtresi reddedildi (%s); filtresiz aranacak.", hata)
                parametreler.pop("max_face_count")
                govde = self._istek("/search", parametreler)
            else:
                raise

        self._semayi_kur(govde)
        _, sonuclar = _ilk_var_olan(govde, UST_DUZEY_ADAYLAR["sonuclar"])
        return [self._modele_cevir(h, terim) for h in (sonuclar or []) if isinstance(h, dict)]

    def ham_ornek(self, terim: str = "volcano") -> dict[str, Any]:
        """--sema-incele icin: ham JSON'un ilk sonucunu dondurur."""
        govde = self._istek("/search", {"type": "models", "q": terim, "sort_by": "-likeCount", "count": 3})
        _, sonuclar = _ilk_var_olan(govde, UST_DUZEY_ADAYLAR["sonuclar"])
        return {
            "ust_duzey_anahtarlar": sorted(govde),
            "sonuc_sayisi": len(sonuclar or []),
            "ilk_sonuc": (sonuclar or [{}])[0],
            "sema_raporu": self._semayi_dogrula(govde).metin(),
        }

    # ------------------------------------------------------------ cevirme

    def _modele_cevir(self, ham: dict[str, Any], terim: str) -> Model:
        yazar = self._al(ham, "yazar") or {}
        lisans = self._al(ham, "lisans") or {}
        kucukler = (self._al(ham, "kucuk_gorsel") or {}).get("images") or []
        etiketler = self._al(ham, "etiketler") or []

        return Model(
            uid=str(self._al(ham, "uid", "")),
            ad=str(self._al(ham, "ad", "")).strip() or "(isimsiz)",
            link=str(self._al(ham, "link", "")),
            embed=str(self._al(ham, "embed", "")),
            yazar_ad=str(yazar.get("displayName") or yazar.get("username") or ""),
            yazar_link=str(yazar.get("profileUrl") or ""),
            begeni=int(self._al(ham, "begeni", 0) or 0),
            goruntulenme=int(self._al(ham, "goruntulenme", 0) or 0),
            ucgen=_tam_sayi_ya_da_none(self._al(ham, "ucgen")),
            animasyon=int(self._al(ham, "animasyon", 0) or 0),
            lisans=str(lisans.get("label") or lisans.get("fullName") or ""),
            lisans_slug=str(lisans.get("slug") or lisans.get("uid") or ""),
            kucuk_gorsel=_kucuk_gorsel_sec(kucukler),
            yas_kisitli=bool(self._al(ham, "yas_kisitli", False)),
            one_cikan=bool(self._al(ham, "one_cikan")),
            etiketler=[
                str(e.get("name") if isinstance(e, dict) else e)
                for e in etiketler
            ][:12],
            terim=terim,
        )


def _tam_sayi_ya_da_none(deger: Any) -> int | None:
    try:
        return int(deger)
    except (TypeError, ValueError):
        return None


def _kucuk_gorsel_sec(gorseller: list[dict[str, Any]], hedef_genislik: int = 448) -> str:
    """Onizleme icin hedefe en yakin genislikteki gorseli secer."""
    uygun = [g for g in gorseller if isinstance(g, dict) and g.get("url")]
    if not uygun:
        return ""
    return min(
        uygun,
        key=lambda g: abs(int(g.get("width") or 0) - hedef_genislik),
    )["url"]
