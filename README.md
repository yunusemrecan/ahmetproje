# Pyvot

**Python sürümlerinizi, paketlerinizi ve projelerinizi tek yerden yönetin.** Windows için masaüstü uygulaması.

> [!NOTE]
> Bu uygulamanın kodu, bir kişinin düz dille verdiği talimatlara göre **yapay zekâ (Anthropic'in Claude modeli)** tarafından yazılmıştır.
>
> *This app's code was written by an AI (Anthropic's Claude), following a person's plain-language instructions.*

## Şu an neler yapabiliyor? (v0.3.0)

**Proje penceresi (Pyvot içinde kod yazma)**
- Proje kendi penceresinde açılır: solda dosya ağacı, ortada sekmeli editör, altta Konsol ve Sorunlar.
- Editör **Monaco**, yani VS Code'un editörü: aynı kısayollar, bul/değiştir, çoklu imleç, kod katlama.
  - Python, JS, HTML, CSS, JSON, TOML, YAML, Markdown dosyaları.
  - `.vscode/settings.json` ayarlarına uyar (sekme genişliği, yazı boyutu, kaydederken biçimlendir).
- **Çalıştır (F5)** `launch.json`'daki ayarı aynen kullanır; VS Code'daki F5 ile aynı şeyi yapar.
  - Konsolda `input()` için yazı yazılabilir.
  - Hata satırlarına tıklayınca dosyanın o satırı açılır.
  - Web projelerinde tarayıcı açılır.
- **Ruff** ile kod denetimi (kaydedince) ve **biçimlendirme** (Shift+Alt+F).
- Önizleme: Markdown, resimler, CSV (tablo), Jupyter defteri (salt okunur).
- Dosya dışarıda (ör. VS Code'da) değişirse kendiliğinden yeniden yüklenir.
- Pencere kapanıp açılınca açık sekmeler geri gelir.

**Projeler**
- Yeni proje sihirbazı: ad ve konum (varsayılan `C:\PyvotProjects`) → şablon → Python sürümü → seçenekler.
- Şablonlar (gruplu):
  - **Temel:** Boş proje, Komut satırı aracı
  - **Veri:** Veri analizi (pandas, matplotlib, Jupyter defteri)
  - **Web:** Web API (FastAPI), Web sitesi (Flask). F5 ile tarayıcı kendiliğinden açılır; örnek pytest testleri içerir.
  - **Masaüstü ve oyun:** Masaüstü uygulaması (PySide6), Oyun (pygame-ce)
- Her projede `pyproject.toml` + `uv.lock` + `.venv`, `.gitignore`, `README.md`, isteğe bağlı Git deposu.
- VS Code dosyaları: doğru Python otomatik seçilir, **F5** ile çalışır (`.vscode/settings.json`, `launch.json`, `tasks.json`, `extensions.json`).
- Proje listesi: sabitleme, arama; **VS Code'da aç**, **Klasörü aç**, **Terminalde aç** (sanal ortam etkin), **Paketleri göster**.
- **Listeden çıkar** (dosyalara dokunmaz) ya da **Çöp kutusuna taşı** (geri alınabilir).
- Var olan klasörü ekleme: `.venv`, `pyproject.toml`, `requirements.txt`, `.git` algılanır; eksikler tamamlanır. Var olan dosyaların üzerine asla yazılmaz.
- **Proje paneli** (sağda):
  - **Özet:** Python sürümü, ortam durumu, `pyproject.toml` / `uv.lock` / `.venv` eşitliği.
  - **Bağımlılıklar:** ana ve geliştirme bağımlılıkları; paket ekle, kaldır, eşitle.
  - **Güncelleme:** istenen sürüm aralığında güncelle, ya da "Büyük sürüme yükselt".
  - **İşlemler:** ortamı onar, Python sürümünü değiştir, `requirements.txt`'den dönüştür ya da ona dışa aktar.

**Python sürümleri**
- Bilgisayardaki tüm Python kurulumlarını otomatik bulur. Arandığı yerler:
  - `py` başlatıcısı
  - Windows kayıt defteri
  - PATH
  - Microsoft Store
  - kurulum klasörleri
  - uv
- Her kurulumun sürümünü, mimarisini, sistem mi sanal ortam mı olduğunu ve varsayılan olup olmadığını gösterir.
- Listede olmayan bir yorumlayıcıyı elle ekleyebilirsiniz.

**Paketler**
- Herhangi bir ortamın paketlerini listeler, filtreler, kurar, kaldırır ve günceller.
- "Güncellemeleri denetle" ile eski paketleri işaretler; tek tıkla hepsini günceller.
- PyPI'de arama yapar (950.000'den fazla paket) ve paket bilgi kartını gösterir: sürümler, lisans, bağımlılıklar, bağlantılar.
- Komut çıktısı canlı akar; uzun süren işlemler durdurulabilir.

**Genel**
- Arka planda [uv](https://github.com/astral-sh/uv) kullanır ve uv uygulamanın içinde gelir. İsterseniz Ayarlar'dan pip'e geçebilirsiniz.
- Türkçe ve İngilizce arayüz; açık, koyu ya da sistemle aynı tema.
- Kısayollar: **Ctrl+1 / 2 / 3 / 4** ile sayfalar arasında geçiş.

## Kurulum

En son test sürümü (**nightly**), `main` dalına yapılan her gönderimden sonra otomatik yayınlanır:

- **[Pyvot-Setup.exe](https://github.com/yunusemrecan/ahmetproje/releases/download/nightly/Pyvot-Setup.exe)**: kurulum sihirbazı. Yönetici izni gerektirmez.
- **[Pyvot-portable.zip](https://github.com/yunusemrecan/ahmetproje/releases/download/nightly/Pyvot-portable.zip)**: kurulumsuz sürüm. Zip'i açıp `Pyvot.exe`'yi çalıştırmanız yeterli.
- Sürüm sayfası ve doğrulama kodları (SHA256): [Releases → nightly](https://github.com/yunusemrecan/ahmetproje/releases/tag/nightly)

Uygulama imzalı olmadığı için Windows SmartScreen ilk açılışta uyarabilir. **Ek bilgi → Yine de çalıştır** ile açabilirsiniz.

Ayarlar `%LOCALAPPDATA%\Pyvot\settings.json` dosyasında tutulur.

## Yol haritası

| Sürüm | İçerik |
|---|---|
| **v0.1** ✅ | Python sürümlerini bulma, paket yönetimi, PyPI arama, Windows kurulum dosyası |
| **v0.2.0** ✅ | Projeler sayfası, yeni proje sihirbazı (Boş, Komut satırı, Veri analizi), VS Code dosyaları, terminal, var olan projeyi ekleme |
| **v0.2.1** ✅ | Proje ayrıntı paneli: bağımlılıklar (ana/geliştirme), eşitleme, ekle/kaldır/güncelle, büyük sürüme yükseltme, ortamı onarma, Python sürümünü değiştirme, requirements.txt dönüştürme/dışa aktarma |
| **v0.2.2** ✅ | Yeni şablonlar: Web API (FastAPI), Web sitesi (Flask), Masaüstü (PySide6), Oyun (pygame-ce); gruplu şablon listesi |
| **v0.3.0** ✅ | Proje penceresi: Monaco editör, dosya ağacı, önizleme, launch.json uyumlu çalıştırma ve konsol, Ruff denetimi ve biçimlendirme |
| v0.4 | Python sürümü kurma/kaldırma (uv ile), `requirements.txt` / `pyproject.toml` içe-dışa aktarma, conda desteği |
| Sonra | Otomatik tamamlama (Pyright), gömülü terminal, Jupyter, uygulama içi güncelleme |

## Geliştirme

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]" uv
python scripts/fetch_monaco.py   # Monaco editörünü indir (bir kez; ~25 MB)
python -m pyvot                  # uygulamayı başlat
pytest                           # testler (-m "not network" ile internetsiz)
```

Windows paketi yerelde şöyle üretilir:

```bash
pip install -r requirements-build.txt
python scripts/fetch_monaco.py
python scripts/write_version_info.py
pyinstaller --noconfirm pyvot.spec
python scripts/bundle_tools.py
iscc /DAppVersion=0.1.0 installer\pyvot.iss   # Inno Setup 6 gerekli
```

### Klasör yapısı

```
src/pyvot/
  core/        Qt kullanmayan iş mantığı: Python keşfi, paketler (uv/pip), PyPI, projeler,
               VS Code dosyaları, terminal, ayarlar
  web/         Monaco editörünün HTML/JS köprüsü (monaco/ klasörü indirilir, git'te yok)
  templates/   proje şablonları ({{name}} ve {{t:anahtar}} yer tutucularıyla)
  ui/          PySide6 arayüzü: sayfalar, arka plan işleri, tema
  i18n.py      Türkçe ve İngilizce metinler
  assets/      simge
tests/         pytest testleri (core + ekransız arayüz testleri)
installer/     Inno Setup betiği ve .ico
scripts/       derleme yardımcıları
```

Yeni bir arayüz metni eklerken onu `i18n.py` içindeki iki dile de ekleyin; testler eksik anahtarı yakalar.

## Lisans

Henüz bir lisans seçilmedi.
