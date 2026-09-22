# Keşif Kutusu · Sketchfab Model Eşleştirme Aracı

ARGE etkinlik listesindeki her kazanım için Sketchfab'den tablet dostu 3B model
önerir. Çıktı: `eslesmeler.xlsx` (paylaşılabilir tablo) + `onizleme.html`
(küçük önizlemeli tek dosya).

## Girdi: kazanimlar.csv

`kazanimlar.csv` (188 kazanım), Drive'daki **"Keşif Kutusu ARGE"** tablosundan
`drive_kazanim_cikar.py` ile üretildi. Tablo birden fazla sekmenin birleşimi
olduğu için betik önce sütun sayısına göre bloklara ayırıyor, yalnızca
"ÖĞRENME ÇIKTILARI" sütunu olan blokları alıyor, birleştirilmiş seviye
hücrelerini ileri-dolduruyor ve tekrarları eliyor.

```bash
python3 drive_kazanim_cikar.py <drive_ciktisi.json> -o kazanimlar.csv
```

Sütunlar: `Seviye; Ünite; Etkinlik; Kazanım; Etkinlik İçeriği`.

> **Neden ünite ve içerik de okunuyor:** bu listede kazanım alanı çoğu zaman
> genel bir müfredat kodudur ("FAB.1. Gündelik yaşamda fenle ilgili olaylara…
> bilimsel gözlem yapabilme") ve konu hakkında hiçbir bilgi taşımaz. Asıl sinyal
> **etkinlik adındadır** ("Lav Lambası", "Köpüren Dinozor"). Araç bu yüzden
> seviye + ünite + etkinlik + kazanım + içeriği birlikte terim üretimine verir.

## Kurulum

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # arama terimi üretimi için
export SKETCHFAB_API_TOKEN=...           # isteğe bağlı, kotayı yükseltir
```

## Kullanım

```bash
# 1) Önce alan adlarını canlı yanıtla doğrula (aşağıdaki nota bakın)
python3 -m sketchfab_eslestirici --sema-incele

# 2) 5 kazanımla dene
python3 -m sketchfab_eslestirici kazanimlar.csv -n 5

# 3) Tamamını çalıştır (yarıda kesilirse aynı komut kaldığı yerden devam eder)
python3 -m sketchfab_eslestirici kazanimlar.csv
```

Çıktılar varsayılan olarak `cikti/` altına yazılır.

### Sık kullanılan seçenekler

| Seçenek | Ne işe yarar |
|---|---|
| `-n, --limit N` | Yalnızca ilk N kazanımı işler (test için) |
| `--model-basina 5` | Kazanım başına kaç model seçilecek |
| `--bekleme 1.0` | İstekler arası en az bekleme (saniye) |
| `--max-ucgen 500000` | API tarafında üçgen sayısı üst sınırı |
| `--sema-incele` | Ham JSON'u ve çözümlenen alan adlarını yazar, çıkar |
| `--kati-sema` | Beklenen alan adları yanıtta yoksa çalışmayı durdurur |
| `--llm-kapali` | LLM yerine sözlük tabanlı yedek terim üretimini kullanır |
| `--terimler-dosyasi t.json` | Gözden geçirilmiş kararları kullanır (LLM yerine) |
| `--hepsini-dene` | Uygunluk kapısını kapatır, her kazanım için terim dener |
| `--asgari-puan 0.5` | Bu puanın altındaki modelleri listelemez (0 = kapalı) |
| `--sahte-veri` | Ağ erişimi olmadan örnek veriyle çalıştırır (yalnızca deneme) |
| `--sutun-kazanim "..."` | Sütun otomatik algılanamazsa elle eşleme |

## Nasıl çalışır

1. **CSV okuma** — `kazanimlar.py`. Ayraç (`;` / `,` / tab) ve kodlama
   (UTF-8, CP1254) otomatik algılanır. Sütun başlıkları Türkçe karakterler
   sadeleştirilerek eşlenir (`Kazanım`, `kazanim`, `learning outcome`…).
2. **Uygunluk kararı + arama terimi üretimi** — `terimler.py`. Anthropic
   Messages API'ye `messages.parse` + Pydantic şeması ile sorulur, böylece dönen
   JSON doğrulanmış olur. Model **önce "bu etkinlik için 3B model gerçekten işe
   yarar mı?"** sorusuna karar verir (aşağıya bakın), yalnızca evet ise terim
   üretir. Kazanımlar 8'erli yığınlar hâlinde gönderilir; bir yığın
   başarısız olursa tek tek, o da olmazsa sözlük yedeğine düşülür.
   Terimler, satırın tamamına (seviye + ünite + etkinlik + kazanım + içerik)
   göre önbelleklenir; bağlam değişirse yeniden üretilir.
3. **Sketchfab araması** — `sketchfab.py`. `GET /v3/search?type=models` +
   `sort_by=-likeCount`. Her yanıt diske önbelleklenir.
4. **Seçim** — `puanlama.py`. Terimlerden gelen adaylar `uid` üzerinden
   tekilleştirilir, puanlanır, en iyi 5'i seçilir.
5. **Çıktı** — `cikti_excel.py` ve `cikti_html.py`.

### Uygunluk kapısı: her kazanıma model önerilmez

Listedeki her etkinliğin 3B modelle anlatılacak bir karşılığı yok. "Duygularımı
Keşfediyorum" (sosyal-duygusal), "Mis Kokulu Kremim" (karıştırma süreci) veya
"Bez Kalemlik Boyama" (el işi) için model önermek, tabloyu alakasız satırlarla
doldurur. Bu yüzden terim üretimi iki aşamalı:

1. `uygun = true/false` — etkinliğin merkezinde, döndürüp inceleyerek öğrenmeyi
   kolaylaştıran **somut** bir nesne/yapı/organizma var mı? Kararsız kalınırsa
   `false`. Az ama isabetli öneri, çok ama alakasız öneriden iyidir.
2. Yalnızca `uygun = true` ise 2–4 terim üretilir.

`uygun = false` olan kazanım için **Sketchfab'e hiç istek gitmez**; kazanım
`Model Önerilmeyenler` sayfasında kısa bir gerekçeyle listelenir ve
`onizleme.html` içinde soluk, kesik çizgili bir blok olarak görünür. Böylece
"atlandı" ile "arandı ama bulunamadı" birbirine karışmaz — ikincisi ayrı bir
`Eşleşmeyenler` sayfasında durur.

Kapıyı kapatmak için `--hepsini-dene`, zayıf eşleşmeleri elemek için
`--asgari-puan 0.5` kullanılabilir.

### Gözden geçirilmiş terim dosyası (`--terimler-dosyasi`)

Uygunluk kararı pedagojik bir karar; son sözü ARGE ekibinin söylemesi gerekir.
`--terimler-dosyasi terimler.json` verildiğinde LLM yerine bu dosyadaki kararlar
kullanılır, dosyada olmayan kazanımlar için normal üretim çalışır.

```json
[
  {"etkinlik": "Köpüren Dinozor", "kazanim": "FAB.1. ...",
   "uygun": true,  "terimler": ["dinosaur", "tyrannosaurus rex"]},
  {"etkinlik": "Duygularımı Keşfediyorum", "kazanim": "SDB1.1. ...",
   "uygun": false, "terimler": [], "neden": "sosyal-duygusal tema"}
]
```

Kayıtlar `(etkinlik, kazanım)` çifti üzerinden eşlenir; satır sırası değişse de
dosya geçerli kalır. Eşleme boşluk ve noktalama farklarına dayanıklıdır (kaynak
tabloda "göre sınıflandırabilme" / "göresınıflandırabilme" gibi yazım farkları
var). `uygun: true` deyip terim vermeyen kayıt elenmiş sayılır.

Depoda `terimler.json` bulunmuyor (kazanım metinlerini içeriyor, repo public).
188 kazanım için hazırlanmış sürüm ayrıca paylaşıldı: 101 kazanım uygun,
87 kazanım elendi.

### Puanlama

| Eksen | Ağırlık | Nasıl hesaplanır |
|---|---|---|
| Beğeni | 0.45 | Logaritmik ölçek, 1000 beğenide doyuma ulaşır |
| Üçgen sayısı | 0.35 | ≤50k = 1.0, 150k = 0.8, 500k = 0.4, ≥1.5M = 0.0 |
| Gömülebilirlik | 0.20 | Lisans + embed URL + animasyon + editör seçimi |

Buna arama teriminin model adı/etiketlerinde geçmesinden gelen en fazla 0.06'lık
bir ilgi bonusu eklenir; puan 0–1 aralığına normalize edilir. Ağırlıklar
`--agirlik-*` ile değiştirilebilir.

Şunlar tamamen elenir: yaş kısıtlı modeller, embed URL'i olmayanlar,
görüntüleyici linki olmayanlar.

### Sözlük yedeğinin sınırı

`--llm-kapali` (veya `ANTHROPIC_API_KEY` yoksa) devreye giren sözlük yedeği, bu
veri setindeki **188 kazanımın 127'sini** karşılıyor. Kalan 61'i, kazanım alanı
genel müfredat kodu olduğu ve etkinlik adı sözlükte bulunmadığı için
karşılayamıyor. Bu durumda araç **bilerek boş terim listesi döndürür** ve o
kazanımı `Model Önerilmeyenler` sayfasında raporlar — Türkçe kelimeleri arama
terimi diye göndermek Sketchfab'de alakasız 5 model getirirdi.

Sözlük yedeğinin uygunluk kararı zayıftır: "Benim Vücudum" gibi aslında modele
çok uygun bir etkinliği sözlükte karşılığı olmadığı için eler, "Bez Kalemlik
Boyama" gibi bir el işi etkinliğine ise "pencil holder" terimini üretir. Doğru
ayıklama için `ANTHROPIC_API_KEY` gerekir.

## Yarıda kesilme ve hız sınırı

- İstekler arasında en az `--bekleme` kadar (varsayılan 1 sn) beklenir,
  üzerine küçük bir rastgelelik eklenir.
- `429` gelirse sunucunun `Retry-After` başlığına uyulur; başlık yoksa üstel
  geri çekilme (2, 4, 8… sn, en çok 60 sn) uygulanır. `5xx` ve ağ hataları da
  aynı şekilde yeniden denenir.
- Her başarılı yanıt `.onbellek/` altına JSON olarak yazılır. Aynı komut tekrar
  çalıştırıldığında önbellekteki istekler ağa hiç çıkmaz — yani yarıda kesilen
  bir çalıştırma baştan başlamaz.
- `Ctrl+C` o anki kazanım bitince temiz çıkar; ikinci `Ctrl+C` hemen durdurur.

## Alan adları hakkında önemli not

Bu araç Sketchfab alan adlarını **tahmin etmez**. `sketchfab.py` içindeki
`ALAN_ADAYLARI` sözlüğü her mantıksal alan için aday API adlarını tutar
(örn. `ucgen` → `faceCount`, `face_count`, `triangleCount`) ve ilk canlı yanıtta
gerçek gövdeye karşı çözümler. Çözülen eşleme günlüğe yazılır; zorunlu alanlar
bulunamazsa uyarı verilir (`--kati-sema` ile çalışma durdurulur).

**İlk çalıştırmadan önce `--sema-incele` çalıştırın.** Bu komut tek bir arama
yapar, ham JSON'u `cikti/sema_ornegi.json` dosyasına yazar ve çözümlenen alan
adlarını ekrana basar. Böylece dökümanla karşılaştırıp doğrulayabilirsiniz:

- Data API v3: <https://sketchfab.com/developers/data-api/v3>
- Referans: <https://docs.sketchfab.com/data-api/v3/index.html>

> Bu araç yazılırken çalışma ortamından `sketchfab.com` adresine ağ erişimi
> kapalıydı; dökümandaki alan adları canlı olarak doğrulanamadı. Tasarım bu
> yüzden "tek bir alan adına bağlanmak" yerine "çalışma anında çözümle ve
> uyuşmazlığı raporla" şeklindedir. `--sema-incele` çıktısı beklenenden
> farklıysa yalnızca `ALAN_ADAYLARI` güncellenir, başka kod değişmez.

> `Üçgen Sayısı` sütunu API'nin `faceCount` alanından gelir. Sketchfab bu değeri
> üçgenleştirilmiş geometri üzerinden verir; yine de `--sema-incele` çıktısında
> `vertexCount` ile birlikte gözle kontrol etmekte fayda var.

## Testler

```bash
python3 -m pytest test_eslestirici.py -q
```

CSV çözümleme, puanlama eğrileri, önbellek kalıcılığı, şema çözümleme,
`429`/`5xx` geri çekilmesi ve desteklenmeyen filtrenin düşürülmesi test edilir.
Testler ağ erişimi gerektirmez.
