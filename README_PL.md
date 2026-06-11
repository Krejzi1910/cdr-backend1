# Color Dice Rigged — Backend Setup (PL)

Kompletna instrukcja postawienia backendu na **Oracle Cloud Always Free**
(rekomendowane, darmowy na zawsze) lub **Render.com** (bez karty, ale usypia).

---

## 🅰️ Wariant A — Oracle Cloud Always Free (REKOMENDOWANY)

### Dlaczego Oracle
- Naprawdę **darmowy na zawsze** (nie 30-dniowy trial)
- **4 rdzenie ARM Ampere + 24 GB RAM** za free (znacznie więcej niż potrzebujesz)
- Twoje stałe publiczne IP
- Działa 24/7 nawet jak śpisz

### Krok 1 — Założenie konta Oracle (≈10 min)

1. Wejdź na https://www.oracle.com/cloud/free/
2. Kliknij **"Start for free"**
3. Wypełnij formularz:
   - **Country/Region**: Poland
   - **Home Region**: wybierz **EU Frankfurt** (najbliższy Polski, niski ping)
   - reszta: imię/nazwisko/email
4. Email weryfikacyjny → kliknij link w mailu
5. **Karta kredytowa do weryfikacji** — Oracle wymaga, ale **nigdy nie pobiorą pieniędzy** dopóki sam nie aktywujesz "Pay As You Go". Konto Free zostaje wieczne.
6. Czekaj na aktywację konta (zwykle ~5 min, czasem do 24h)

### Krok 2 — Stworzenie instancji ARM

Po zalogowaniu się do **Oracle Cloud Console**:

1. Menu (≡) → **Compute** → **Instances** → **Create Instance**
2. **Name**: `cdr-backend` (cokolwiek)
3. **Image and shape** → kliknij **Edit**:
   - **Image**: `Canonical Ubuntu 22.04` (kliknij Change image)
   - **Shape**: kliknij Change shape →
     - **Shape series**: **Ampere** (ARM)
     - **Shape**: `VM.Standard.A1.Flex`
     - OCPU: **2**, Memory: **12 GB** (więcej niż dość, mieścisz się w free quota)
   - Apply
4. **Networking**:
   - **Primary network**: zostaw domyślne (nowy VCN się sam utworzy)
   - **Public IPv4 address**: ✅ **Assign a public IPv4 address** (musi być zaznaczone!)
5. **SSH keys**:
   - Wybierz **"Generate a key pair for me"**
   - Kliknij **Save private key** → zapisz plik `.key` w bezpiecznym miejscu (to Twój klucz do SSH)
   - Kliknij **Save public key** też dla pewności
6. Na dole kliknij **Create**

Po ~1 min instancja będzie **Running**. Skopiuj **Public IPv4 Address** (np. `132.226.x.x`).

### Krok 3 — Otwarcie portu 8000 w Oracle Security List

Oracle ma firewall na poziomie sieci, **musisz go ręcznie otworzyć**:

1. W Console: kliknij na swoją instancję
2. W sekcji **Primary VNIC** → kliknij link **Subnet** (np. `Public Subnet-vcn-xxxx`)
3. W szczegółach subnetu: sekcja **Security Lists** → kliknij **Default Security List for vcn-xxxx**
4. Sekcja **Ingress Rules** → kliknij **Add Ingress Rules**
5. Wypełnij:
   - **Source CIDR**: `0.0.0.0/0`
   - **IP Protocol**: TCP
   - **Destination Port Range**: `8000`
   - Description: `CDR Backend`
6. **Add Ingress Rules** → gotowe.

### Krok 4 — SSH do serwera

**Windows (PowerShell)**:
```powershell
ssh -i C:\sciezka\do\klucz.key ubuntu@132.226.x.x
```

**Mac/Linux (Terminal)**:
```bash
chmod 600 ~/Downloads/klucz.key
ssh -i ~/Downloads/klucz.key ubuntu@132.226.x.x
```

Pierwsze połączenie: wpisz `yes` żeby zaakceptować fingerprint.

> Jeśli widzisz `Permission denied (publickey)` — upewnij się że ścieżka do klucza jest poprawna i że plik ma uprawnienia `600` (Mac/Linux: `chmod 600 klucz.key`).

### Krok 5 — Instalacja backendu

Teraz jesteś zalogowany jako `ubuntu@cdr-backend`. Skopiuj kod backendu na serwer:

**Opcja A: scp z lokalnego komputera** (najprościej):
```bash
# z Twojego komputera (NIE z serwera)
scp -i klucz.key -r ./cdr-backend ubuntu@132.226.x.x:/home/ubuntu/
```

**Opcja B: bezpośrednio na serwerze** (jeśli masz pliki na GitHub itp.) — zostawiam wybór.

Następnie **na serwerze** (przez SSH):
```bash
cd /home/ubuntu/cdr-backend
sudo bash install.sh
```

Skrypt zapyta o port (Enter dla 8000) i wszystko sam zrobi. Na końcu pokaże:
```
========================================================
  Backend installed and running.
========================================================

  Backend URL:  http://132.226.x.x:8000
  API Key:      d4c8f9a3b2e1...
```

**Skopiuj URL i API Key** — wkleisz je do rozszerzenia za chwilę.

### Krok 6 — Test z laptopa

W przeglądarce wpisz: `http://132.226.x.x:8000/api/health`

Powinieneś zobaczyć: `{"ok":true,"uptime_sec":X,"version":"1.0","auth_required":true}`

Jeśli **strona nie ładuje się / timeout** → wróć do Kroku 3 (Security List w Oracle).

### Krok 7 — Konfiguracja w rozszerzeniu

1. Załaduj rozszerzenie v2.0 w Chrome (`chrome://extensions/` → Load unpacked)
2. Otwórz `https://www.online-dice.com/`
3. Alt+D → kliknij przycisk **"Backend"** (nowy, na dole panelu)
4. Wpisz **Backend URL**: `http://132.226.x.x:8000`
5. Wpisz **API Key**: `d4c8f9a3b2e1...` (to co pokazał installer)
6. Kliknij **Save & Test** → powinno pokazać `✓ Backend OK · uptime Xs`

**Gotowe.** Teraz klik **Save Settings** = backend zwróci real ID natychmiast.

### Krok 8 — Pierwsza godzina "rozgrzewania"

Backend zaczyna od pustej bazy. Pierwsze 30-60 min:
- 2 dice: będą działać od razu (36 combos to bardzo mało)
- 3 dice: ~5-10 min pełnego pokrycia
- 4 dice: ~1-2h pełnego pokrycia
- 5-6 dice: pierwsze trafienia po 2-3h

Możesz monitorować postęp w panelu **Find Real ID** — pole "Pokrycie".

Backend dział 24/7 więc rano obudzisz się z **prawie pełnym indeksem**.

### Komendy serwisowe (na serwerze)

```bash
# zobacz logi na żywo
sudo journalctl -fu cdr-backend

# restart
sudo systemctl restart cdr-backend

# status
sudo systemctl status cdr-backend

# rozmiar bazy
ls -lh /var/lib/cdr/cdr.sqlite

# liczba tokenów w bazie
sudo sqlite3 /var/lib/cdr/cdr.sqlite "SELECT COUNT(*) FROM rolls;"
```

---

## 🅱️ Wariant B — Render.com (bez karty)

### Plusy / minusy
- ✅ **Bez karty kredytowej**, login przez GitHub
- ✅ Setup w 5 min
- ❌ **Usypia po 15 min nieaktywności** — pierwszy request po przerwie potrwa ~30s zanim się obudzi
- ❌ Limit 750 godzin/mies darmowych (wystarcza na 1 instancję 24/7)

### Krok 1 — Repo na GitHubie
1. Załóż konto na github.com (jeśli nie masz)
2. Stwórz **publiczne** repo `cdr-backend`
3. Wgraj do niego pliki z folderu `/app/cdr-backend/` (przez web UI → drag & drop)
4. Dodatkowo stwórz plik `render.yaml`:
   ```yaml
   services:
     - type: web
       name: cdr-backend
       runtime: python
       buildCommand: pip install -r requirements.txt
       startCommand: python server.py
       envVars:
         - key: CDR_API_KEY
           generateValue: true
         - key: CDR_DB_PATH
           value: /tmp/cdr.sqlite
         - key: CDR_PORT
           value: "10000"
   ```

### Krok 2 — Render
1. Zaloguj się na https://render.com przez GitHub
2. **New** → **Web Service** → wybierz Twoje repo `cdr-backend`
3. Render auto-wykryje `render.yaml`, kliknij **Deploy**
4. Po ~3 min serwis będzie running. URL: `https://cdr-backend-xxxx.onrender.com`
5. **Settings** → **Environment** → znajdź `CDR_API_KEY` → skopiuj wartość

### Krok 3 — Konfiguracja rozszerzenia
Tak samo jak Wariant A Krok 7, tylko URL bez portu:
- Backend URL: `https://cdr-backend-xxxx.onrender.com`
- API Key: (skopiowany z Render)

---

## ⚠️ Częste problemy

### "Backend offline" w rozszerzeniu
- Sprawdź czy w przeglądarce otwarcie `http://TWOJE_IP:8000/api/health` zwraca JSON.
- Jeśli nie → port nie jest otwarty (Oracle Security List) lub serwis nie wstał (`journalctl -fu cdr-backend`).

### "Zły API key"
- Skopiuj key bez spacji. Hex 32 znaki.

### Backend zwraca `not-found-yet` ciągle
- Cache backendu jest pusty dla tej kombinacji. Daj mu 5-10 min i spróbuj znowu.
- Sprawdź `coverage` w popupie — jak rośnie, znaczy że farmer działa.

### Backend wpada w cooldown (tier > 0 w stats)
- Cloudflare blokuje IP Oracle. Backend już go zwalnia automatycznie.
- Jeśli stale tier=2 → spróbuj zmienić region Oracle (np. UK London zamiast Frankfurt) lub przejdź na Render (inne IP).

### Mam większy/szybszy serwer i chcę więcej req/s
- Edytuj `/opt/cdr-backend/farmer.py`: zmniejsz wartości w `TIERS`.
- `sudo systemctl restart cdr-backend`

---

## 📁 Pliki w paczce

```
cdr-backend/
├── server.py          # FastAPI app (REST API)
├── farmer.py          # background farmer z adaptive throttling
├── db.py              # SQLite wrapper
├── requirements.txt   # 3 dependencies (FastAPI, uvicorn, httpx)
├── install.sh         # automatyczny installer dla Ubuntu
└── README_PL.md       # ten plik
```

W razie pytań — zapytaj w czacie, krok po kroku to wszystko popchniemy.
