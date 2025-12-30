# Farm Planner

Lēmumu atbalsta sistēma lauksaimniecības kultūru plānošanai.

## Local run

Lokāla palaišana projektā:

1. Izveidojiet virtuālo vidi:
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# vai
.venv\Scripts\activate  # Windows
```

2. Instalējiet atkarības:
```bash
pip install -r requirements.txt
```

3. Palaidiet aplikāciju:
```bash
streamlit run app.py
```

Aplikācija būs pieejama: http://localhost:8501

## Lietotāji un autentifikācija

Sistēma izmanto lokālu autentifikāciju ar e-pasta adresi un paroli.

### Reģistrācija un pieslēgšanās

- Katram lietotājam ir savs konts ar unikālu e-pasta adresi
- Paroles tiek glabātas kā bcrypt hash (nekad nav glabātas kā teksts)
- Katrs lietotājs redz tikai savus datus (lauki, sējumu vēsture)

### Remember me

- Ja lietotājs atzīmē "Atcerēties mani šajā ierīcē", viņš automātiski paliek ielogots 30 dienas
- Ielogošanās beidzas tikai, kad lietotājs nospiež "Logout" vai izdzēš pārlūka datus

### Datu izolācija

- Visi lauki un sējumu ieraksti ir saistīti ar lietotāja ID
- Lietotāji nevar redzēt citu lietotāju datus
- Katram lietotājam ir savs neatkarīgs darbs ar sistēmu

### Streamlit Cloud datubāze

- Streamlit Cloud demo vidē SQLite datubāze var tikt resetota, kad aplikācija tiek restartēta
- Visi dati tiek glabāti lokālajā SQLite datubāzē (`data/farm.db`)
- Produkcijas vidē ieteicams izmantot PostgreSQL ar `DATABASE_URL` vides mainīgo

## Deploy (Streamlit Cloud)

Projektu var izvietot uz Streamlit Cloud.

### Priekšnosacījumi

1. GitHub repozitorijs ar projektu
2. Streamlit Cloud konts (bez maksas plāns pieejams)

### Deploy soļi

1. **Pieslēdziet GitHub repozitoriju Streamlit Cloud:**
   - Ielogojieties [Streamlit Cloud](https://streamlit.io/cloud)
   - Noklikšķiniet "New app"
   - Izvēlieties GitHub repozitoriju ar šo projektu

2. **Konfigurācija:**
   - **Main file:** `app.py`
   - **Branch:** `main` vai `master` (atkarībā no jūsu repo)

3. **Nepieciešamie faili:**
   - `requirements.txt` - jābūt repo saknē
   - `data/*` - visi datu faili (crops.json, prices_lv.csv, u.c.)
   - `.streamlit/config.toml` - Streamlit konfigurācija

4. **Deploy:**
   - Noklikšķiniet "Deploy"
   - Streamlit Cloud automātiski instalēs atkarības un palaidīs aplikāciju
   - Pēc veiksmīga deploy, jūs saņemsiet URL, kurā aplikācija būs pieejama

### Piezīmes

- Visi datu faili no `data/` direktorijas tiek iekļauti deploy
- Sistēma izmanto SQLite datubāzi lokāli (`data/farm.db`)
- Ja nepieciešams PostgreSQL, iestatiet `DATABASE_URL` vides mainīgo Streamlit Cloud iestatījumos

## Instalācija

1. Izveidojiet virtuālo vidi:
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# vai
.venv\Scripts\activate  # Windows
```

2. Instalējiet atkarības:
```bash
pip install -r requirements.txt
```

## Palaišana

### Galvenā aplikācija

```bash
streamlit run app.py
```

### Testa skripti

#### Cenu testa skripts

Testē EC Agri-food Data Portal cenu ielādi:

```bash
python scripts/test_prices.py
```

Skripts izvada tabulu ar kolonnām:
- **Kultūra** - kultūras nosaukums
- **Cena (EUR/t)** - cena eiro uz tonnu
- **Datums** - datums, kad cena tika atjaunota
- **Avots** - cenu avots (EC agridata)

Piemērs izvades:
```
Ielādē cenas no EC Agri-food Data Portal...
------------------------------------------------------------

Kultūra        Cena (EUR/t)   Datums       Avots               
------------------------------------------------------------
Kvieši         210.50         2025-01-15   EC agridata         
Mieži           195.00         2025-01-14   EC agridata         
Auzas           180.75         2025-01-13   EC agridata         
------------------------------------------------------------
Kopā atrastas cenas: 3/3
```

## Struktūra

- `app.py` - Streamlit UI aplikācija
- `src/` - Galvenais kods
  - `models.py` - Datu modeļi
  - `planner.py` - Plānošanas loģika
  - `market_prices.py` - EC agridata integrācija
  - `storage.py` - Datu glabāšana
- `data/` - Datu faili
  - `crops.json` - Kultūru katalogs
- `scripts/` - Palīgskripti
  - `test_prices.py` - Cenu testa skripts

## Cenu dati

Sistēma izmanto vairākus cenu avotus, lai nodrošinātu precīzus peļņas aprēķinus:

1. **ES tirgus cenas** - Sistēma automātiski ielādē aktuālās cenas no ES Agri-food Data Portal kultūrām, kurām ir pieejami publiski tirgus dati (piemēram, kvieši, mieži, auzas). Šīs cenas tiek atjauninātas regulāri un atspoguļo reālo tirgus situāciju.

2. **Lokālās cenas** - Kultūrām, kurām nav pieejami publiski tirgus dati (piemēram, zirņi, pupas), sistēma izmanto lokālās cenas no oficiālās statistikas vai kooperatīvu vidējām cenām. Šīs cenas tiek glabātas `data/local_prices.json` failā.

3. **Lokālais katalogs** - Ja nav pieejami ne ES tirgus dati, ne lokālās cenas, sistēma izmanto cenas no `data/crops.json` faila. Šīs ir noklusējuma cenas, kas tiek izmantotas kā pēdējais fallback variants.

Sistēma vienmēr cenšas izmantot visaktuālākos datus, bet nekad nekrīt, ja ārējie avoti nav pieejami - tādā gadījumā tiek izmantotas lokālās vērtības.

## Kultūru cenas

- Sistēma atbalsta plašu kultūru klāstu (graudaugi, pākšaugi, eļļaugi, sakņaugi, zālāji u.c.).
- Kultūrām ar publiskiem tirgus datiem izmanto ES cenas.
- Pārējām tiek izmantotas lokālās vai proxy cenas (no līdzīgām kultūrām).
- Cenu avots vienmēr tiek parādīts lietotājam (ES tirgus, lokāls vai proxy), lai būtu skaidrs, no kurienes nāk dati.

## Funkcijas

- Lauku pārvaldība
- Sējumu vēstures ievade
- Kultūru ieteikumi balstīti uz:
  - Augsnes veidu
  - Sējumu vēsturi (rotācija)
  - Peļņas aprēķiniem
  - EC agridata cenām
- Peļņas prognozes (3 gadi)
- Scenāriju analīze

## Deploy uz Render

Projektu var izvietot uz Render kā Docker Web Service.

### Priekšnosacījumi

1. GitHub repozitorijs ar projektu
2. Render konts (bez maksas plāns pieejams)

### Deploy soļi

1. **Pieslēdziet GitHub repozitoriju Render:**
   - Ielogojieties Render dashboard
   - Noklikšķiniet "New +" un izvēlieties "Web Service"
   - Izvēlieties "Connect GitHub" un autorizējiet Render piekļuvi jūsu GitHub kontam
   - Izvēlieties repozitoriju ar šo projektu

2. **Izveidojiet PostgreSQL datubāzi:**
   - Render dashboard, noklikšķiniet "New +" un izvēlieties "PostgreSQL"
   - Izvēlieties bez maksas plānu
   - Pēc izveides, Render automātiski izveidos `DATABASE_URL` vides mainīgo

3. **Konfigurējiet Docker deploy:**
   - Render automātiski atpazīs Dockerfile un izmantos Docker deploy
   - Ja nepieciešams, manuāli norādiet "Docker" kā Environment
   - Render automātiski izveidos Docker image no Dockerfile

4. **Iestatījumi:**
   - **Name:** Jebkurš vēlamais nosaukums
   - **Region:** Izvēlieties tuvāko reģionu
   - **Branch:** `main` vai `master` (atkarībā no jūsu repo)
   - **Root Directory:** Atstājiet tukšu (ja projekts repo saknē)
   - **Dockerfile Path:** `Dockerfile` (noklusējuma vērtība)
   - **Docker Context:** `.` (punkts, kas nozīmē pašreizējo direktoriju)

5. **Environment Variables:**
   - **`DATABASE_URL`** - Render automātiski pievieno šo mainīgo, kad izveidojat PostgreSQL datubāzi. Nav nepieciešams manuāli pievienot.
   - **`PORT`** - Render automātiski nodrošina šo mainīgo
   - **`FARM_ADMIN_USER`** (opcionāli) - Admin lietotājvārds pirmajam lietotājam
   - **`FARM_ADMIN_PASS`** (opcionāli) - Admin parole pirmajam lietotājam

6. **Pievienojiet DATABASE_URL Web Service:**
   - Web Service iestatījumos, noklikšķiniet "Environment"
   - Pievienojiet `DATABASE_URL` no PostgreSQL datubāzes (Render automātiski piedāvā to pievienot)
   - Vai arī manuāli kopējiet `DATABASE_URL` no PostgreSQL datubāzes iestatījumiem

7. **Deploy:**
   - Noklikšķiniet "Create Web Service"
   - Render sāks būvēt Docker image un deploy aplikāciju
   - Pēc veiksmīga deploy, jūs saņemsiet URL, kurā aplikācija būs pieejama

### Datu glabāšana

Sistēma automātiski izmanto PostgreSQL, ja `DATABASE_URL` vides mainīgais ir iestatīts:

- **Render (production):** Render automātiski nodrošina `DATABASE_URL` no PostgreSQL datubāzes. Sistēma automātiski izmanto PostgreSQL.
- **Lokāli (development):** Ja `DATABASE_URL` nav iestatīts, sistēma izmanto SQLite kā fallback (`data/farm.db`).

### Svarīgi iestatījumi Dockerfile

- **`--server.address=0.0.0.0`** - Nepieciešams, lai Streamlit aplikācija būtu pieejama no ārējām saites. Noklusējuma vērtība `localhost` darbojas tikai lokāli.

- **`--server.port=${PORT}`** - Render automātiski nodrošina `PORT` vides mainīgo, kas norāda, uz kura porta jāklausās. Dockerfile izmanto šo mainīgo, lai aplikācija darbojas uz pareizā porta.

- **`--server.headless=true`** - Neatver pārlūkprogrammu automātiski, kas ir nepieciešams servera vidē.

### Pēc deploy

- Render automātiski atjaunos aplikāciju, kad veiksiet push uz GitHub
- Logs ir pieejami Render dashboard
- Ja nepieciešams, varat konfigurēt custom domain
- Visi dati tiek glabāti PostgreSQL datubāzē

## Deploy uz Streamlit Cloud

Projektu var izvietot uz Streamlit Cloud.

### Priekšnosacījumi

1. GitHub repozitorijs ar projektu
2. Streamlit Cloud konts (bez maksas plāns pieejams)
3. PostgreSQL datubāze (Render, Supabase, vai cita)

### Deploy soļi

1. **Pieslēdziet GitHub repozitoriju Streamlit Cloud:**
   - Ielogojieties Streamlit Cloud
   - Noklikšķiniet "New app"
   - Izvēlieties repozitoriju un branch

2. **Konfigurējiet secrets:**
   - Streamlit Cloud dashboard, noklikšķiniet uz jūsu aplikācijas
   - Izvēlieties "Settings" → "Secrets"
   - Pievienojiet:
     ```toml
     DB_URL = "postgresql://user:password@host:port/database"
     ```

3. **Deploy:**
   - Streamlit Cloud automātiski izveidos aplikāciju
   - Pēc veiksmīga deploy, jūs saņemsiet URL

### Piezīmes

- Pirmā deploy var aizņemt vairākas minūtes, kamēr tiek būvēts Docker image
- Bez maksas plāns var ietvert ierobežojumus (piemēram, aplikācija "aizmieg" pēc neaktivitātes)
- PostgreSQL datubāze tiek automātiski izmantota, ja `DATABASE_URL` ir iestatīts
- Lokāli var izmantot SQLite vai arī lokālu PostgreSQL, iestatot `DATABASE_URL` vides mainīgo

