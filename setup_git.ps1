# Git Setup Script for Farm Planner
# Izpildiet šo skriptu no PROJEKTS direktorijas

Write-Host "Setting up Git repository for Farm Planner..." -ForegroundColor Green

# Pārbaudiet, vai esat projekta direktorijā
if (-not (Test-Path "app.py")) {
    Write-Host "ERROR: app.py nav atrasts! Lūdzu, pārejiet uz PROJEKTS direktoriju." -ForegroundColor Red
    Write-Host "Piemērs: cd 'C:\Users\uldis\OneDrive - Rīgas Tehniskā Universitāte\PROJEKTS'" -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ Projekta direktorija atrasta" -ForegroundColor Green

# Izdzēsiet git repozitoriju no mājas direktorijas, ja eksistē
if (Test-Path "$env:USERPROFILE\.git") {
    Write-Host "Dzēš veco git repozitoriju no mājas direktorijas..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "$env:USERPROFILE\.git" -ErrorAction SilentlyContinue
}

# Inicializējiet git projekta direktorijā
if (Test-Path ".git") {
    Write-Host "Git repozitorijs jau eksistē projekta direktorijā" -ForegroundColor Yellow
} else {
    Write-Host "Inicializē git repozitoriju..." -ForegroundColor Green
    git init
}

# Iestatiet git lietotāja informāciju (ja vēl nav)
$gitEmail = git config user.email 2>$null
$gitName = git config user.name 2>$null

if (-not $gitEmail) {
    Write-Host "Iestatiet git lietotāja e-pastu:" -ForegroundColor Yellow
    $email = Read-Host "E-pasts"
    git config user.email $email
}

if (-not $gitName) {
    Write-Host "Iestatiet git lietotāja vārdu:" -ForegroundColor Yellow
    $name = Read-Host "Vārds"
    git config user.name $name
}

# Pievienojiet failus
Write-Host "`nPievieno failus..." -ForegroundColor Green
git add app.py README.md requirements.txt Dockerfile compose.yaml compose.debug.yaml cli.py cli_app.py ui_app.py GITHUB_SETUP.md
git add src/ scripts/ .streamlit/ .gitignore
git add data/*.json data/*.csv 2>$null

# Pārbaudiet statusu
Write-Host "`nGit status:" -ForegroundColor Green
git status --short

# Commit
Write-Host "`nVai vēlaties izveidot commit? (Y/N)" -ForegroundColor Yellow
$response = Read-Host
if ($response -eq "Y" -or $response -eq "y") {
    git commit -m "Initial commit: Farm Planner application"
    Write-Host "`n✓ Commit izveidots!" -ForegroundColor Green
    Write-Host "`nNākamie soļi:" -ForegroundColor Cyan
    Write-Host "1. Izveidojiet GitHub repozitoriju: https://github.com/new" -ForegroundColor White
    Write-Host "2. Pievienojiet remote:" -ForegroundColor White
    Write-Host "   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git" -ForegroundColor Gray
    Write-Host "3. Augšupielādējiet:" -ForegroundColor White
    Write-Host "   git branch -M main" -ForegroundColor Gray
    Write-Host "   git push -u origin main" -ForegroundColor Gray
} else {
    Write-Host "Commit nav izveidots. Varat to izdarīt vēlāk ar: git commit -m 'Your message'" -ForegroundColor Yellow
}
