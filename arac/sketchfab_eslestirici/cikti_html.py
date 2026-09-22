"""onizleme.html uretimi: tek dosya, kucuk onizleme gorselleriyle."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .kazanimlar import Kazanim
from .sketchfab import Model

SAYFA = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Keşif Kutusu · Model Eşleşmeleri</title>
<style>
:root {{
  --arka: #f6f7f9; --kart: #ffffff; --metin: #16202b; --soluk: #5b6b7c;
  --cizgi: #e1e6ec; --vurgu: #1f6feb; --uyari-arka: #fff4d6; --uyari-metin: #7a5300;
  --hafif: #1a7f52; --orta: #9a6a00; --agir: #b23b3b;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --arka: #11161c; --kart: #1a222b; --metin: #e6edf3; --soluk: #97a6b6;
    --cizgi: #2b3743; --vurgu: #5aa0ff; --uyari-arka: #3d3213; --uyari-metin: #ffd98a;
    --hafif: #58d39a; --orta: #e0b341; --agir: #ff8c8c;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--arka); color: var(--metin);
  font: 15px/1.5 -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}}
.kapsayici {{ max-width: 1180px; margin: 0 auto; padding: 24px 16px 64px; }}
header h1 {{ font-size: 24px; margin: 0 0 6px; }}
header p {{ color: var(--soluk); margin: 0 0 18px; }}
.uyari {{
  background: var(--uyari-arka); color: var(--uyari-metin); border-radius: 10px;
  padding: 12px 16px; margin-bottom: 20px; font-weight: 600;
}}
.arac-cubugu {{
  position: sticky; top: 0; z-index: 5; background: var(--arka);
  padding: 10px 0 14px; border-bottom: 1px solid var(--cizgi); margin-bottom: 22px;
}}
#arama {{
  width: 100%; padding: 11px 14px; font-size: 15px; color: var(--metin);
  background: var(--kart); border: 1px solid var(--cizgi); border-radius: 9px;
}}
#arama:focus {{ outline: 2px solid var(--vurgu); outline-offset: 1px; }}
.sayac {{ color: var(--soluk); font-size: 13px; margin-top: 8px; }}
.seviye-basligi {{
  font-size: 13px; text-transform: uppercase; letter-spacing: .08em;
  color: var(--soluk); margin: 30px 0 10px; font-weight: 700;
}}
.kazanim-blogu {{
  background: var(--kart); border: 1px solid var(--cizgi); border-radius: 12px;
  padding: 16px 16px 6px; margin-bottom: 18px;
}}
.etkinlik {{ font-size: 12px; color: var(--vurgu); font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }}
.kazanim-metni {{ font-size: 16px; font-weight: 600; margin: 4px 0 8px; }}
.terimler {{ font-size: 12px; color: var(--soluk); margin-bottom: 14px; }}
.terimler code {{
  background: var(--arka); border: 1px solid var(--cizgi); border-radius: 5px;
  padding: 1px 6px; margin-right: 5px; font-size: 11px;
}}
.izgara {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(215px, 1fr)); gap: 14px; padding-bottom: 12px; }}
.kart {{
  border: 1px solid var(--cizgi); border-radius: 10px; overflow: hidden;
  background: var(--arka); display: flex; flex-direction: column;
}}
.kart img {{ width: 100%; aspect-ratio: 16/9; object-fit: cover; background: var(--cizgi); display: block; }}
.kart .govde {{ padding: 10px 11px 12px; display: flex; flex-direction: column; gap: 5px; flex: 1; }}
.kart .ad {{ font-weight: 600; font-size: 13.5px; line-height: 1.35; }}
.kart .yazar, .kart .lisans {{ font-size: 11.5px; color: var(--soluk); }}
.olcumler {{ display: flex; flex-wrap: wrap; gap: 6px; font-size: 11px; margin-top: 2px; }}
.rozet {{ background: var(--kart); border: 1px solid var(--cizgi); border-radius: 20px; padding: 2px 8px; }}
.yuk-hafif {{ color: var(--hafif); border-color: currentColor; }}
.yuk-orta {{ color: var(--orta); border-color: currentColor; }}
.yuk-agir {{ color: var(--agir); border-color: currentColor; }}
.baglantilar {{ margin-top: auto; padding-top: 8px; display: flex; gap: 10px; font-size: 12px; }}
.baglantilar a {{ color: var(--vurgu); text-decoration: none; font-weight: 600; }}
.baglantilar a:hover {{ text-decoration: underline; }}
.bos {{ color: var(--soluk); font-style: italic; padding: 4px 0 14px; }}
.gizli {{ display: none !important; }}
footer {{ margin-top: 36px; color: var(--soluk); font-size: 12px; border-top: 1px solid var(--cizgi); padding-top: 14px; }}
</style>
</head>
<body>
<div class="kapsayici">
<header>
  <h1>Keşif Kutusu · Sketchfab Model Eşleşmeleri</h1>
  <p>{ozet}</p>
</header>
{uyari}
<div class="arac-cubugu">
  <input id="arama" type="search" placeholder="Kazanım, etkinlik, model adı veya terimle filtrele…" autocomplete="off">
  <div class="sayac" id="sayac"></div>
</div>
{govde}
<footer>{altbilgi}</footer>
</div>
<script>
const katla = (s) => s.replace(/[İIı]/g, "i").toLowerCase();
const kutu = document.getElementById("arama");
const sayac = document.getElementById("sayac");
const bloklar = Array.from(document.querySelectorAll(".kazanim-blogu"));
const toplam = bloklar.length;

function filtrele() {{
  const sorgu = katla(kutu.value.trim());
  let gorunen = 0;
  for (const blok of bloklar) {{
    const uygun = !sorgu || blok.dataset.arama.includes(sorgu);
    blok.classList.toggle("gizli", !uygun);
    if (uygun) gorunen++;
  }}
  for (const baslik of document.querySelectorAll(".seviye-bolumu")) {{
    const acik = baslik.querySelectorAll(".kazanim-blogu:not(.gizli)").length > 0;
    baslik.classList.toggle("gizli", !acik);
  }}
  sayac.textContent = gorunen === toplam
    ? `${{toplam}} kazanım gösteriliyor`
    : `${{gorunen}} / ${{toplam}} kazanım gösteriliyor`;
}}
kutu.addEventListener("input", filtrele);
filtrele();
</script>
</body>
</html>
"""


def _k(metin: Any) -> str:
    return html.escape(str(metin or ""), quote=True)


def _katla(metin: str) -> str:
    """Turkce'ye duyarli, JS tarafiyla birebir ayni kucuk harf katlamasi.

    Python'un .lower()'i ile JS'in toLocaleLowerCase("tr")'si "I"/"İ" harflerinde
    ayrisir; filtre kutusunun yazdigi metin ile data-arama'daki metin uyusmazsa
    arama sessizce bos sonuc verir. Iki taraf da once noktali/noktasiz I'leri
    duz "i"ye cevirip sonra kucultur.
    """
    for kaynak in ("İ", "I", "ı"):
        metin = metin.replace(kaynak, "i")
    return metin.lower()


def _tablet_sinifi(ucgen: int | None) -> tuple[str, str]:
    if ucgen is None:
        return "", "üçgen sayısı bilinmiyor"
    if ucgen <= 150_000:
        return "yuk-hafif", f"{ucgen:,} üçgen · hafif".replace(",", ".")
    if ucgen <= 500_000:
        return "yuk-orta", f"{ucgen:,} üçgen · orta".replace(",", ".")
    return "yuk-agir", f"{ucgen:,} üçgen · ağır".replace(",", ".")


def _kart(model: Model) -> str:
    sinif, etiket = _tablet_sinifi(model.ucgen)
    gorsel = (
        f'<img src="{_k(model.kucuk_gorsel)}" alt="{_k(model.ad)} önizleme" loading="lazy">'
        if model.kucuk_gorsel
        else '<img alt="önizleme yok">'
    )
    yazar = (
        f'<a href="{_k(model.yazar_link)}" target="_blank" rel="noopener">{_k(model.yazar_ad)}</a>'
        if model.yazar_link
        else _k(model.yazar_ad)
    )
    begeni = f"{model.begeni:,}".replace(",", ".")
    return f"""      <article class="kart">
        {gorsel}
        <div class="govde">
          <div class="ad">{_k(model.ad)}</div>
          <div class="yazar">{yazar}</div>
          <div class="olcumler">
            <span class="rozet">♥ {begeni}</span>
            <span class="rozet {sinif}">{_k(etiket)}</span>
            {'<span class="rozet">animasyonlu</span>' if model.animasyon else ''}
          </div>
          <div class="lisans">{_k(model.lisans or 'lisans bilgisi yok')} · terim: {_k(model.terim)}</div>
          <div class="baglantilar">
            <a href="{_k(model.link)}" target="_blank" rel="noopener">Sketchfab</a>
            <a href="{_k(model.embed)}" target="_blank" rel="noopener">Embed</a>
          </div>
        </div>
      </article>"""


def _blok(kazanim: Kazanim, modeller: list[Model], terimler: list[str]) -> str:
    arama_metni = _katla(
        " ".join(
            [kazanim.seviye, kazanim.etkinlik, kazanim.kazanim, *terimler]
            + [m.ad for m in modeller]
            + [m.yazar_ad for m in modeller]
        )
    )
    terim_html = "".join(f"<code>{_k(t)}</code>" for t in terimler) or "<em>terim üretilemedi</em>"
    if modeller:
        icerik = '<div class="izgara">\n' + "\n".join(_kart(m) for m in modeller) + "\n    </div>"
    else:
        icerik = '<div class="bos">Bu kazanım için uygun model bulunamadı.</div>'
    return f"""  <section class="kazanim-blogu" data-arama="{_k(arama_metni)}">
    <div class="etkinlik">{_k(kazanim.etkinlik)}</div>
    <div class="kazanim-metni">{_k(kazanim.kazanim)}</div>
    <div class="terimler">Arama terimleri: {terim_html}</div>
    {icerik}
  </section>"""


def yaz(
    yol: Path,
    satirlar: list[tuple[Kazanim, list[Model]]],
    terimler: dict[str, list[str]],
    ustbilgi: dict[str, Any],
    sahte_veri: bool = False,
) -> None:
    # Seviyeye gore grupla, girdideki sirayi koru.
    gruplar: dict[str, list[tuple[Kazanim, list[Model]]]] = {}
    for kazanim, modeller in satirlar:
        gruplar.setdefault(kazanim.seviye or "Seviye belirtilmemiş", []).append((kazanim, modeller))

    bolumler = []
    for seviye, ogeler in gruplar.items():
        bloklar = "\n".join(_blok(k, m, terimler.get(k.kimlik, [])) for k, m in ogeler)
        bolumler.append(
            f'<div class="seviye-bolumu">\n'
            f'  <div class="seviye-basligi">{_k(seviye)} · {len(ogeler)} kazanım</div>\n'
            f"{bloklar}\n</div>"
        )

    toplam_model = sum(len(m) for _, m in satirlar)
    ozet = (
        f"{len(satirlar)} kazanım · {toplam_model} model önerisi · "
        f"kazanım başına en iyi {ustbilgi.get('model_basina', 5)} model "
        f"(beğeni, üçgen sayısı ve gömülebilirliğe göre sıralandı)"
    )
    uyari = (
        '<div class="uyari">ÖRNEK VERİ: Bu sayfa --sahte-veri modunda üretildi. '
        "Kartlar gerçek Sketchfab modelleri değildir; yalnızca boru hattını göstermek içindir.</div>"
        if sahte_veri
        else ""
    )
    altbilgi = (
        f"Girdi: {_k(ustbilgi.get('girdi'))} · Üretim: {_k(ustbilgi.get('tarih'))} · "
        f"Terim üretimi: {_k(ustbilgi.get('terim_kaynagi'))} · "
        f"Sketchfab isteği: {_k(ustbilgi.get('istek_sayisi'))}"
    )

    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(
        SAYFA.format(ozet=_k(ozet), uyari=uyari, govde="\n".join(bolumler), altbilgi=altbilgi),
        encoding="utf-8",
    )
