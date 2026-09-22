"""Komut satiri arayuzu."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import signal
import sys
from pathlib import Path

from . import __version__, kazanimlar as kz, terimler as trm
from .cache import Onbellek
from .cikti_excel import yaz as excel_yaz
from .cikti_html import yaz as html_yaz
from .config import ARAMA_SAYFA_LIMITI, VARSAYILAN_MODEL, Ayarlar, ortamdan_token
from .puanlama import en_iyileri_sec
from .sketchfab import Model, SemaUyusmazligi, SketchfabIstemcisi

log = logging.getLogger("eslestirici")

_DURDUR = False


def _sinyal(imza, cerceve) -> None:  # noqa: ARG001
    """Ctrl+C: mevcut kazanim bitince temiz cik; onbellek zaten diskte."""
    global _DURDUR
    if _DURDUR:
        sys.exit(130)
    _DURDUR = True
    log.warning("Durdurma istendi; su anki kazanim bitince cikilacak (tekrar Ctrl+C = hemen).")


def ayristir(argv: list[str] | None = None) -> argparse.Namespace:
    a = argparse.ArgumentParser(
        prog="sketchfab-eslestirici",
        description="Kesif Kutusu LMS kazanimlarini Sketchfab 3B modelleriyle eslestirir.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    a.add_argument("girdi", nargs="?", default="kazanimlar.csv", type=Path,
                   help="ARGE etkinlik listesi (CSV)")
    a.add_argument("-c", "--cikti", type=Path, default=Path("cikti"),
                   help="Ciktilarin yazilacagi dizin")
    a.add_argument("--onbellek", type=Path, default=Path(".onbellek"),
                   help="Onbellek dizini (yarida kesilen calistirma buradan devam eder)")
    a.add_argument("-n", "--limit", type=int, default=None,
                   help="Yalnizca ilk N kazanimi isle (test icin)")
    a.add_argument("--model-basina", type=int, default=5,
                   help="Kazanim basina secilecek model sayisi")
    a.add_argument("--aday", type=int, default=ARAMA_SAYFA_LIMITI,
                   help=f"Her terim icin cekilecek aday sayisi (en fazla {ARAMA_SAYFA_LIMITI})")

    g = a.add_argument_group("terim uretimi (Anthropic)")
    g.add_argument("--llm-model", default=VARSAYILAN_MODEL, help="Anthropic model kimligi")
    g.add_argument("--llm-yigin", type=int, default=8, help="Tek istekte kac kazanim")
    g.add_argument("--llm-kapali", action="store_true",
                   help="LLM kullanma; sozluk tabanli yedek terim uretimini kullan")

    s = a.add_argument_group("sketchfab")
    s.add_argument("--bekleme", type=float, default=1.0,
                   help="Istekler arasi en az bekleme (saniye)")
    s.add_argument("--azami-deneme", type=int, default=5, help="Bir istek icin azami deneme")
    s.add_argument("--max-ucgen", type=int, default=None,
                   help="API tarafinda ucgen sayisi ust siniri (max_face_count)")
    s.add_argument("--kati-sema", action="store_true",
                   help="Beklenen alan adlari yanitta yoksa calismayi durdur")
    s.add_argument("--sema-incele", action="store_true",
                   help="Tek bir arama yapip ham JSON semasini yazdirir ve cikar")
    s.add_argument("--sahte-veri", action="store_true",
                   help="Ag erisimi olmadan ornek veriyle calistir (yalnizca deneme amacli)")

    p = a.add_argument_group("puanlama")
    p.add_argument("--agirlik-begeni", type=float, default=0.45)
    p.add_argument("--agirlik-ucgen", type=float, default=0.35)
    p.add_argument("--agirlik-gomulebilirlik", type=float, default=0.20)

    x = a.add_argument_group("sutun eslemesi (otomatik algilama yetmezse)")
    x.add_argument("--sutun-seviye")
    x.add_argument("--sutun-etkinlik")
    x.add_argument("--sutun-kazanim")

    a.add_argument("--onbellek-omru", type=float, default=None,
                   help="Onbellek kaydinin gecerlilik suresi (gun)")
    a.add_argument("-v", "--ayrintili", action="store_true", help="Ayrintili gunluk")
    a.add_argument("--surum", action="version", version=f"%(prog)s {__version__}")
    return a.parse_args(argv)


def _istemci_kur(ayarlar: Ayarlar, onbellek: Onbellek) -> SketchfabIstemcisi:
    if ayarlar.sahte_veri:
        from .sahte import SahteIstemci

        log.warning("SAHTE VERI MODU: sonuclar gercek Sketchfab modelleri degildir.")
        return SahteIstemci(onbellek, kati_sema=ayarlar.kati_sema)
    return SketchfabIstemcisi(
        onbellek,
        token=ayarlar.sketchfab_token,
        bekleme=ayarlar.bekleme,
        azami_deneme=ayarlar.azami_deneme,
        kati_sema=ayarlar.kati_sema,
    )


def calistir(ayarlar: Ayarlar) -> int:
    onbellek = Onbellek(ayarlar.onbellek_dizini, omur_gun=ayarlar.onbellek_omru_gun)
    istemci = _istemci_kur(ayarlar, onbellek)

    # 1) Kazanimlari oku
    tum_kazanimlar, esleme = kz.oku(ayarlar.girdi, ayarlar.sutun_eslemesi)
    log.info("%s: %d kazanim okundu (sutunlar: %s)",
             ayarlar.girdi, len(tum_kazanimlar), esleme)
    if not tum_kazanimlar:
        log.error("Islenecek kazanim yok.")
        return 1
    secilenler = tum_kazanimlar[: ayarlar.limit] if ayarlar.limit else tum_kazanimlar

    # 2) Arama terimleri
    llm_kapali = ayarlar.llm_kapali or not _anthropic_kimlik_var()
    if ayarlar.llm_kapali:
        kaynak = "sozluk (--llm-kapali)"
    elif llm_kapali:
        kaynak = "sozluk (ANTHROPIC_API_KEY bulunamadi)"
        log.warning("ANTHROPIC_API_KEY yok; sozluk tabanli yedek terim uretimi kullanilacak.")
    else:
        kaynak = f"Anthropic {ayarlar.llm_model}"
    log.info("Terim uretimi: %s", kaynak)
    terim_haritasi = trm.uret(
        secilenler, onbellek, ayarlar.llm_model, ayarlar.llm_yigin, llm_kapali
    )

    # 3-4) Arama + secim
    satirlar: list[tuple[kz.Kazanim, list[Model]]] = []
    for sira, kazanim in enumerate(secilenler, start=1):
        if _DURDUR:
            log.warning("Durduruldu: %d/%d kazanim islendi; onbellek korundu.",
                        sira - 1, len(secilenler))
            break
        kazanim_terimleri = terim_haritasi.get(kazanim.kimlik, [])
        adaylar: list[Model] = []
        for terim in kazanim_terimleri:
            try:
                adaylar.extend(istemci.ara(terim, ayarlar.aday_sayisi, ayarlar.max_ucgen))
            except SemaUyusmazligi:
                raise
            except Exception as hata:
                log.error("'%s' aramasi basarisiz: %s", terim, hata)
        en_iyiler, elenen = en_iyileri_sec(adaylar, ayarlar)
        satirlar.append((kazanim, en_iyiler))
        log.info("[%d/%d] %-42.42s | terim: %-28.28s | aday %3d -> %d%s",
                 sira, len(secilenler), kazanim.kazanim,
                 ", ".join(kazanim_terimleri), len(adaylar), len(en_iyiler),
                 f" (elenen: {elenen})" if elenen else "")

    # 5) Ciktilar
    ustbilgi = {
        "girdi": str(ayarlar.girdi),
        "tarih": dt.datetime.now().strftime("%d.%m.%Y %H:%M"),
        "terim_kaynagi": kaynak,
        "istek_sayisi": istemci.istek_sayisi,
        "onbellek": onbellek.ozet(),
        "model_basina": ayarlar.model_basina,
        "agirlik_begeni": ayarlar.agirlik_begeni,
        "agirlik_ucgen": ayarlar.agirlik_ucgen,
        "agirlik_gomulebilirlik": ayarlar.agirlik_gomulebilirlik,
    }
    excel_yaz(ayarlar.xlsx_yolu, satirlar, terim_haritasi, ustbilgi, ayarlar.sahte_veri)
    html_yaz(ayarlar.html_yolu, satirlar, terim_haritasi, ustbilgi, ayarlar.sahte_veri)

    toplam = sum(len(m) for _, m in satirlar)
    bos = sum(1 for _, m in satirlar if not m)
    print()
    print(f"  {len(satirlar)} kazanım işlendi · {toplam} model önerisi · {bos} kazanım boş")
    print(f"  {istemci.istek_sayisi} Sketchfab isteği · {onbellek.ozet()}")
    print(f"  → {ayarlar.xlsx_yolu}")
    print(f"  → {ayarlar.html_yolu}")
    if ayarlar.sahte_veri:
        print("  ! ÖRNEK VERİ modu: çıktılar gerçek Sketchfab sonucu değildir.")
    return 0


def _anthropic_kimlik_var() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def main(argv: list[str] | None = None) -> int:
    a = ayristir(argv)
    logging.basicConfig(
        level=logging.DEBUG if a.ayrintili else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )
    signal.signal(signal.SIGINT, _sinyal)

    ayarlar = Ayarlar(
        girdi=a.girdi,
        cikti_dizini=a.cikti,
        onbellek_dizini=a.onbellek,
        limit=a.limit,
        model_basina=a.model_basina,
        aday_sayisi=min(a.aday, ARAMA_SAYFA_LIMITI),
        llm_model=a.llm_model,
        llm_yigin=a.llm_yigin,
        llm_kapali=a.llm_kapali,
        sketchfab_token=ortamdan_token(),
        bekleme=a.bekleme,
        azami_deneme=a.azami_deneme,
        max_ucgen=a.max_ucgen,
        sahte_veri=a.sahte_veri,
        agirlik_begeni=a.agirlik_begeni,
        agirlik_ucgen=a.agirlik_ucgen,
        agirlik_gomulebilirlik=a.agirlik_gomulebilirlik,
        kati_sema=a.kati_sema,
        onbellek_omru_gun=a.onbellek_omru,
        sutun_eslemesi={
            k: v for k, v in (
                ("seviye", a.sutun_seviye),
                ("etkinlik", a.sutun_etkinlik),
                ("kazanim", a.sutun_kazanim),
            ) if v
        }
        or None,
    )

    if a.sema_incele:
        onbellek = Onbellek(ayarlar.onbellek_dizini)
        istemci = _istemci_kur(ayarlar, onbellek)
        ornek = istemci.ham_ornek()
        ayarlar.cikti_dizini.mkdir(parents=True, exist_ok=True)
        yol = ayarlar.cikti_dizini / "sema_ornegi.json"
        yol.write_text(json.dumps(ornek, ensure_ascii=False, indent=2), encoding="utf-8")
        print(ornek["sema_raporu"])
        print(f"\nHam örnek yazıldı: {yol}")
        return 0

    if not ayarlar.girdi.exists():
        log.error("Girdi dosyasi bulunamadi: %s", ayarlar.girdi)
        return 2

    try:
        return calistir(ayarlar)
    except SemaUyusmazligi as hata:
        log.error("Sema uyusmazligi:\n%s", hata)
        return 3
    except KeyboardInterrupt:
        return 130
