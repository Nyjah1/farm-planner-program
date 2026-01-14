# GitHub Setup Instructions

Lai augšupielādētu projektu uz GitHub, izpildiet šādas komandas PowerShell terminālī:

## 1. Pārejiet uz projekta direktoriju

```powershell
cd "C:\Users\uldis\OneDrive - Rīgas Tehniskā Universitāte\PROJEKTS"
```

Vai arī atveriet PowerShell tieši projekta direktorijā (labā peles poga uz PROJEKTS mapes → "Open in Terminal" vai "Open PowerShell window here").

## 2. Inicializējiet Git repozitoriju (ja vēl nav izdarīts)

```powershell
git init
```

## 3. Iestatiet Git lietotāja informāciju (ja vēl nav izdarīts)

```powershell
git config user.email "your-email@example.com"
git config user.name "Your Name"
```

## 4. Pievienojiet failus

```powershell
git add app.py README.md requirements.txt Dockerfile compose.yaml compose.debug.yaml cli.py cli_app.py ui_app.py
git add src/
git add scripts/
git add .streamlit/
git add .gitignore
git add data/*.json data/*.csv
```

## 5. Izveidojiet pirmo commit

```powershell
git commit -m "Initial commit: Farm Planner application"
```

## 6. Izveidojiet GitHub repozitoriju

1. Ejiet uz https://github.com
2. Noklikšķiniet uz "+" → "New repository"
3. Ievadiet repozitorija nosaukumu (piemēram, "farm-planner")
4. Izvēlieties "Public" vai "Private"
5. **NEIEZĪMĒJIET** "Initialize this repository with a README" (jo mums jau ir README)
6. Noklikšķiniet "Create repository"

## 7. Pievienojiet GitHub remote un augšupielādējiet

```powershell
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

**Piezīme:** Aizstājiet `YOUR_USERNAME` ar jūsu GitHub lietotājvārdu un `YOUR_REPO_NAME` ar jūsu repozitorija nosaukumu.

## Alternatīva: Izmantojot SSH (ja esat iestatījuši SSH atslēgas)

```powershell
git remote add origin git@github.com:YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

## Ja rodas problēmas ar autentifikāciju

Ja GitHub prasa autentifikāciju, varat izmantot:
- **Personal Access Token** (Settings → Developer settings → Personal access tokens → Generate new token)
- **GitHub CLI** (`gh auth login`)
- **SSH keys**

## Nākamie soļi pēc augšupielādes

1. Pārbaudiet, vai visi faili ir augšupielādēti: https://github.com/YOUR_USERNAME/YOUR_REPO_NAME
2. Ja nepieciešams, pievienojiet `.gitignore` failu, lai neiekļautu nevajadzīgus failus (`.venv/`, `*.db`, u.c.)
3. Pēc tam varat izmantot GitHub Actions, Streamlit Cloud vai Render deploy
