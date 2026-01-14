# Push uz GitHub - Instrukcijas

## ⚠️ Svarīgi

Git repozitorijs jāinicializē **tieši PROJEKTS mapē**, nevis mājas direktorijā.

## Soļi

### 1. Atveriet PowerShell tieši PROJEKTS mapē

**Vienkāršākais veids:**
1. Atveriet File Explorer
2. Dodieties uz: `C:\Users\uldis\OneDrive - Rīgas Tehniskā Universitāte\PROJEKTS`
3. Noklikšķiniet ar labo peles taustiņu uz tukšas vietas mapē
4. Izvēlieties **"Open in Terminal"** vai **"Open PowerShell window here"**

### 2. Izdzēsiet veco git repozitoriju no mājas direktorijas (ja eksistē)

```powershell
Remove-Item -Recurse -Force "$env:USERPROFILE\.git" -ErrorAction SilentlyContinue
```

### 3. Inicializējiet git projekta direktorijā

```powershell
git init
```

### 4. Iestatiet lietotāja informāciju

```powershell
git config user.email "your-email@example.com"
git config user.name "Your Name"
```

### 5. Pievienojiet projekta failus

```powershell
git add app.py README.md requirements.txt Dockerfile compose.yaml compose.debug.yaml cli.py cli_app.py ui_app.py GITHUB_SETUP.md setup_git.ps1
git add src/
git add scripts/
git add .streamlit/
git add .gitignore
git add data/*.json data/*.csv
```

### 6. Izveidojiet commit

```powershell
git commit -m "Initial commit: Farm Planner application"
```

### 7. Izveidojiet GitHub repozitoriju

1. Ejiet uz: https://github.com/new
2. Ievadiet repozitorija nosaukumu (piemēram, `farm-planner`)
3. Izvēlieties **Public** vai **Private**
4. **NEIEZĪMĒJIET** "Initialize this repository with a README"
5. Noklikšķiniet **"Create repository"**

### 8. Pievienojiet GitHub remote un push

```powershell
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

**Piezīme:** Aizstājiet `YOUR_USERNAME` ar jūsu GitHub lietotājvārdu un `YOUR_REPO_NAME` ar jūsu repozitorija nosaukumu.

## Alternatīva: Izmantojiet setup_git.ps1 skriptu

Ja esat projekta direktorijā, varat izpildīt:

```powershell
.\setup_git.ps1
```

Skripts automātiski sagatavo visu, bet jums joprojām būs jāpievieno GitHub remote un jāpush manuāli.

## Ja rodas problēmas ar autentifikāciju

GitHub var prasīt autentifikāciju. Izmantojiet vienu no šiem:

1. **Personal Access Token:**
   - Settings → Developer settings → Personal access tokens → Generate new token
   - Izmantojiet token kā paroli, kad GitHub prasa autentifikāciju

2. **GitHub CLI:**
   ```powershell
   gh auth login
   ```

3. **SSH keys:**
   - Iestatiet SSH atslēgas un izmantojiet SSH URL: `git@github.com:USERNAME/REPO.git`
