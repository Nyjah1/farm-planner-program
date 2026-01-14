# 🌾 Farm Planner

**Lēmumu atbalsta sistēma lauksaimniecības lauku uzskaitei un plānošanai**

Farm Planner ir Python balstīta tīmekļa lietotne, kas palīdz lauksaimniekiem:

- **pārvaldīt laukus**
- **veidot lauka darbu vēsturi**
- **analizēt kultūru rotāciju**
- **strādāt ar saviem datiem drošā, lietotājam izolētā vidē**

Lietotne ir izstrādāta kā mācību noslēguma projekts, demonstrējot pilnu izstrādes ciklu un GenAI izmantošanu programmatūras izstrādē.

## 📦 Iegūšana no GitHub

Ja lejupielādējat projektu no GitHub kā ZIP vai klonējat ar `git clone`, direktorijas nosaukumam var būt piedēklis `-main`, piemēram:

```
farm-planner-main
```

Tas ir normāli un neietekmē aplikācijas darbību.

Pēc lejupielādes:

```bash
cd farm-planner-main
```

## 🖥️ Lokāla palaišana (Local run)

### 1. Virtuālās vides izveide

```bash
python -m venv .venv
```

**Aktivizācija:**

**Linux / macOS:**
```bash
source .venv/bin/activate
```

**Windows:**
```bash
.venv\Scripts\activate
```

⚠️ **Ja Windows bloķē skriptus**, palaidiet PowerShell kā Administrator un izpildiet:

```powershell
Set-ExecutionPolicy RemoteSigned
```

### 2. Atkarību instalēšana

```bash
pip install -r requirements.txt
```

### 3. Aplikācijas palaišana

```bash
streamlit run app.py
```

Aplikācija būs pieejama:

**http://localhost:8501**

## 🪟 Windows specifiskas piezīmes

Ja UI elementi nerādās vai aplikācija nestartējas:

1. **Pārbaudiet, vai Streamlit ir instalēts:**
   ```bash
   pip install streamlit
   ```

2. **Pārbaudiet, vai eksistē `data/` direktorija:**
   ```bash
   mkdir data
   ```

3. **Ja nepieciešams, palaidiet ar pilnu ceļu:**
   ```bash
   python -m streamlit run app.py
   ```

4. **Ja redzat datubāzes kļūdas:**
   - pārliecinieties, ka `data/` ir rakstīšanas tiesības
   - pārbaudiet, vai antivīruss nebloķē failus

## 👤 Lietotāji un autentifikācija

Sistēma izmanto lokālu autentifikāciju ar lietotājvārdu un paroli.

### Reģistrācija un pieslēgšanās

- katram lietotājam ir savs konts
- paroles tiek glabātas kā bcrypt hash
- katrs lietotājs redz tikai savus datus

### "Atcerēties mani"

- lietotājs var palikt ielogots konkrētajā ierīcē
- sesija saglabājas līdz logout vai pārlūka datu dzēšanai

### Datu izolācija

- visi lauki un ieraksti ir piesaistīti lietotāja ID
- nav iespējams redzēt citu lietotāju informāciju

## 🗂️ Funkcionalitāte

### Lauku pārvaldība

- Lauka pievienošana ar nosaukumu, platību un augsnes veidu
- Lauku saraksts ar detalizētu informāciju

### Lauka vēsture

- datums
- darbības veids (sēšana, apstrāde, kulšana u.c.)
- brīvas formas piezīmes

### Kultūru rotācijas uzskaite

- Sējumu vēstures ievade
- Rotācijas noteikumu ievērošana
- Ieteikumi nākamajam gadam

### Kultūru ieteikumi

- Ieteikumi balstīti uz:
  - Augsnes veidu
  - Sējumu vēsturi (rotācija)
  - Peļņas aprēķiniem
  - EC agridata cenām
- Peļņas prognozes (3 gadi)
- Scenāriju analīze

### Kultūru katalogs

- Plašs kultūru klāsts
- Cenu informācija no ES tirgus datiem
- Favorītu sistēma

### Lietotāju autentifikācija

- Droša reģistrācija un pieslēgšanās
- Datu izolācija starp lietotājiem

### Darbs lokāli

- Lokāla izmantošana ar SQLite datubāzi

## 🗃️ Datu glabāšana

### Lokāli (development)

**SQLite datubāze:**
- `data/farm.db`

### Production vide

- Ja ir iestatīts `DATABASE_URL`, sistēma automātiski izmanto PostgreSQL
- Ja nav – tiek izmantots SQLite kā fallback

## 📁 Projekta struktūra

```
app.py                  # Galvenā Streamlit aplikācija
src/
 ├── auth.py             # Autentifikācija
 ├── models.py           # Datu modeļi
 ├── storage.py          # Datu glabāšana
 ├── planner.py          # Plānošanas loģika
 ├── market_prices.py    # EC agridata integrācija
 ├── price_provider.py   # Cenu piegādātājs
 ├── profit.py           # Peļņas aprēķini
 ├── analytics.py        # Analītika
 └── ...
data/
 ├── crops.json          # Kultūru katalogs
 ├── crops_csp.json      # CSP kultūras
 ├── prices_lv.csv       # Lokālās cenas
 └── farm.db             # SQLite datubāze
scripts/
 └── test_prices.py      # Testa skripti
requirements.txt         # Python atkarības
```

## 🔧 Cenu dati

Sistēma izmanto vairākus cenu avotus, lai nodrošinātu precīzus peļņas aprēķinus:

1. **ES tirgus cenas** - Automātiski ielādē aktuālās cenas no ES Agri-food Data Portal kultūrām, kurām ir pieejami publiski tirgus dati (piemēram, kvieši, mieži, auzas).

2. **Lokālās cenas** - Kultūrām, kurām nav pieejami publiski tirgus dati (piemēram, zirņi, pupas), sistēma izmanto lokālās cenas no oficiālās statistikas vai kooperatīvu vidējām cenām.

3. **Lokālais katalogs** - Ja nav pieejami ne ES tirgus dati, ne lokālās cenas, sistēma izmanto cenas no `data/crops.json` faila.

Sistēma vienmēr cenšas izmantot visaktuālākos datus, bet nekad nekrīt, ja ārējie avoti nav pieejami - tādā gadījumā tiek izmantotas lokālās vērtības.

## 📝 Testa skripti

### Cenu testa skripts

Testē EC Agri-food Data Portal cenu ielādi:

```bash
python scripts/test_prices.py
```

## 📄 Licences

Šis projekts ir izstrādāts kā mācību noslēguma projekts.
