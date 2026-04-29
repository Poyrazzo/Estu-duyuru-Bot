# ESTÜ Duyuru Botu

Eskişehir Teknik Üniversitesi öğrencileri için otomatik duyuru takip botu.  
Canvas (OYS) derslerinizi ve Bilgisayar Mühendisliği bölüm sitesini izler — yeni duyuru geldiğinde tam içeriğiyle birlikte anında Telegram bildirimi gönderir.

---

## Ne Yapar?

| Kaynak | Ne İzler? |
|---|---|
| **Canvas (OYS)** | Kayıtlı olduğunuz tüm derslerin duyuruları |
| **ceng.eskisehir.edu.tr** | Bilgisayar Mühendisliği bölüm duyuruları |

Her yeni duyuru için Telegram'a şunları gönderir:
- Kaynak ders / site adı
- Duyuru başlığı
- Yayınlanma tarihi ve saati
- Tam metin içerik
- Doğrudan bağlantı

---

## Nasıl Çalışır?

**GitHub Actions** üzerinde her **15 dakikada bir** otomatik olarak çalışır.  
Sunucu, Raspberry Pi veya telefon gerekmez — tamamen ücretsizdir.

Duyuru ID'leri bir SQLite veritabanında saklanır; aynı duyuru için asla iki kez bildirim gelmez.

---

## Kurulum

### 1. Gereksinimler

- GitHub hesabı
- Telegram hesabı
- ESTÜ Canvas hesabı (`estuoys.eskisehir.edu.tr`)

### 2. Telegram Botu Oluştur

1. Telegram'da **@BotFather**'a mesaj at → `/newbot`
2. Bot adı ve kullanıcı adı belirle
3. Verilen **API Token**'ı kopyala
4. **@userinfobot**'a `/start` göndererek kendi **Chat ID**'ni öğren

### 3. Canvas Erişim Jetonu Al

1. `https://estuoys.eskisehir.edu.tr` adresine giriş yap
2. **Hesap → Ayarlar → Erişim Jetonları → Jeton Ekle**
3. Oluşturulan jetonu kopyala *(yalnızca bir kez gösterilir)*

### 4. Repoyu Fork'la ve Secrets Ekle

Bu repoyu fork'la, ardından **Settings → Secrets and variables → Actions** bölümünden şu 3 secret'ı ekle:

| Secret Adı | Değer |
|---|---|
| `TELEGRAM_TOKEN` | BotFather'dan aldığın token |
| `TELEGRAM_CHAT_ID` | @userinfobot'tan aldığın ID |
| `CANVAS_TOKEN` | Canvas'tan aldığın erişim jetonu |

### 5. İlk Çalıştırma

**Actions → ESTÜ Canvas Duyuru Kontrolü → Run workflow**

İlk çalıştırmada mevcut tüm duyurular "görüldü" olarak işaretlenir.  
Bundan sonra yalnızca yeni gelenlerde bildirim alırsın.

---

## Yerel Çalıştırma (Opsiyonel)

```bash
# Kurulum
./setup.sh

# config.json dosyasını doldur (config.json.example'a bak)
cp config.json.example config.json
# ... değerleri gir ...

# Botu başlat (sürekli döngü)
./run.sh

# Ya da tek seferlik kontrol
venv/bin/python run_once.py
```

---

## Proje Yapısı

```
├── bot.py          → Ana döngü (yerel çalıştırma için)
├── run_once.py     → Tek seferlik kontrol (GitHub Actions kullanır)
├── scraper.py      → Canvas API + bölüm sitesi scraper
├── db.py           → SQLite (görülen ID'ler + bildirim kuyruğu)
├── notifier.py     → Telegram Bot API entegrasyonu
├── quiet_hours.py  → Sessiz saat mantığı
└── .github/
    └── workflows/
        └── check_announcements.yml  → 15 dakikalık GitHub Actions zamanlaması
```

---

## Güvenlik

- `config.json` `.gitignore`'a eklenmiştir — tokenlar asla repoya yüklenmez
- GitHub Actions tokenları **Secrets** üzerinden güvenli biçimde aktarılır
- Repo herkese açık olsa bile kimlik bilgileriniz korunur

---

## Katkı

ESTÜ öğrencileri için yapıldı. Fork'layıp kendi üniversitene uyarlamak istersen Canvas API'si kullanan her kurumda çalışır — `config.json` içindeki `base_url`'i değiştirmen yeterli.
