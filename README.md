# Farm Planner

**Lēmumu atbalsta sistēma lauksaimniecības lauku uzskaitei un kultūru plānošanai.**

Farm Planner ir Python balstīta tīmekļa lietotne, kas palīdz lauksaimniekiem:

- **pārvaldīt laukus**
- **veidot lauku darbu un sējumu vēsturi**
- **analizēt kultūru rotāciju**
- **plānot nākamos gadus, balstoties uz datiem**
- **strādāt ar saviem datiem drošā, lietotājam izolētā vidē**

Lietotne izstrādāta kā noslēguma projekts, demonstrējot pilnu programmatūras izstrādes ciklu un ģeneratīvā mākslīgā intelekta (GenAI) izmantošanu.

## Iegūšana no GitHub

Ja lejupielādējat projektu no GitHub kā ZIP vai klonējat ar `git clone`, direktorijas nosaukumam var būt piedēklis `-main` (piemēram, `farm-planner-main`).

Tas ir normāli un neietekmē aplikācijas darbību.

Pēc lejupielādes:

```bash
cd farm-planner-main
```

## Lokāla palaišana (Local run)

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

**Ja Windows bloķē skriptus:**
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

## Windows specifiskas piezīmes

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
   - pārbaudiet, vai antivīruss vai firewall nebloķē failu piekļuvi

## Lietotāji un autentifikācija

Sistēma izmanto lokālu autentifikāciju ar lietotājvārdu un paroli.

- Katram lietotājam ir savs konts
- Paroles tiek glabātas kā bcrypt hash
- Katrs lietotājs redz tikai savus datus
- Pieejama opcija "Atcerēties mani", kas saglabā sesiju konkrētajā ierīcē
- Sesija beidzas tikai pēc logout vai pārlūka datu dzēšanas

**Datu izolācija:**
- Visi lauki un ieraksti ir piesaistīti lietotāja ID
- Nav iespējams redzēt citu lietotāju informāciju

## Funkcionalitāte

- **Lauku pārvaldība** (nosaukums, platība, augsnes veids)
- **Lauku darbu un sējumu vēsture**
- **Kultūru rotācijas uzskaite**
- **Kultūru ieteikumi**, balstīti uz:
  - augsnes veidu
  - sējumu vēsturi
  - peļņas aprēķiniem
  - ES tirgus datiem
- **Peļņas prognozes** (3 gadi)
- **Scenāriju analīze**
- **Kultūru katalogs**
- **Favorītu sistēma**
- **Lietotāju autentifikācija un datu izolācija**
- **Darbs lokāli ar SQLite datubāzi**

## Galvenās tehnoloģijas un bibliotēkas

### Programmēšanas valoda

**Python 3**

Izvēlēta tās elastības, plašā bibliotēku atbalsta un piemērotības dēļ datu analīzei un biznesa loģikai.

### Lietotāja interfeiss

**Streamlit**

Izmantots kā web lietotāja interfeiss:
- formu, tabulu un datu vizualizācijai
- lietotāju sesiju pārvaldībai
- ātrai prototipēšanai un izmaiņu ieviešanai

### Datu glabāšana

**SQLite**
- Noklusējuma datubāze lokālai izstrādei
- Datu fails: `data/farm.db`

**PostgreSQL**
- Automātiski tiek izmantots, ja ir iestatīts `DATABASE_URL`
- Paredzēts produkcijas videi (Render, Streamlit Cloud)

### Autentifikācija un drošība

**bcrypt**
- Paroļu hashēšanai
- Nodrošina, ka paroles netiek glabātas tīrā tekstā

### Datu apstrāde un analītika

**pandas**
- CSV un tabulu datu apstrādei
- Izmantots cenu datu analīzei

**NumPy**
- Matemātiskiem aprēķiniem un prognozēm

### Ārējie datu avoti

**EC Agri-food Data Portal**
- ES publiskie tirgus cenu dati
- Izmantots kviešiem, miežiem un auzām
- Implementēts ar kļūdu apstrādi un fallback mehānismiem

### API un tīkla pieprasījumi

**requests**
- HTTP pieprasījumiem uz ārējiem datu avotiem

### Konteinerizācija un izvietošana

**Docker**
- Vienotas vides nodrošināšanai lokāli un produkcijā

**Render / Streamlit Cloud**
- Aplikācijas izvietošanai ar automātisku deploy no GitHub

### GenAI izmantošana

**ChatGPT (GenAI)**

Izmantots kā palīgrīks:
- arhitektūras plānošanai
- koda refaktorēšanai
- dokumentācijas strukturēšanai

Gala risinājumi un lēmumi pieņemti manuāli.

## Datu glabāšana

### Lokāli:
- SQLite (`data/farm.db`)

### Produkcijā:
- PostgreSQL, ja ir iestatīts `DATABASE_URL`
- Ja nav, sistēma automātiski izmanto SQLite kā fallback

## Projekta struktūra

```
app.py                  # Galvenā Streamlit aplikācija
src/
 ├── auth.py             # Autentifikācija
 ├── models.py           # Datu modeļi
 ├── storage.py          # Datu glabāšana
 ├── planner.py          # Plānošanas loģika
 ├── market_prices.py    # ES cenu datu integrācija
 ├── price_provider.py   # Cenu piegādātājs
 ├── profit.py           # Peļņas aprēķini
 ├── analytics.py        # Analītika
data/
 ├── crops.json          # Kultūru katalogs
 ├── prices_lv.csv       # Lokālās cenas
 └── farm.db             # SQLite datubāze
scripts/
 └── test_prices.py      # Cenu testa skripts
```

## Testa skripti

**Cenu datu pārbaude:**

```bash
python scripts/test_prices.py
```
