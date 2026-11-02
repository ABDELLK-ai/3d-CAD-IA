# 3D CAD Studio — Générateur CAO Paramétrique par IA

## Description
Application web Python professionnelle qui transforme une description en **langage naturel** d'une pièce mécanique en un modèle 3D paramétrique B-Rep exact, avec :
- 🤖 **IA Gemini** pour interpréter la description technique et générer du code CadQuery
- ⚙️ **CadQuery (OpenCASCADE OCCT)** pour modéliser la géométrie solide exacte (B-Rep)
- 🔭 **Viewer 3D interactif Three.js** : OrbitControls fluide, matériaux configurables (Bleu CAO, Inox, Laiton, Carbone, Orange atelier), arêtes mécaniques, capture HD
- 📊 **Analyse physique & géométrique** : Bounding box X×Y×Z, volume exact (cm³), surface totale (cm²), estimation des masses (Acier, Aluminium, PLA impression 3D, Titane) et centre de gravité
- ✏️ **Éditeur CadQuery Live** : Modifiez le code directement dans l'interface et recalculez la géométrie 3D en 1 clic
- 📥 **Export STEP (AP203/AP214)** compatible CATIA V5, CATIA 3DEXPERIENCE, SolidWorks, Autodesk Fusion et FreeCAD
- 📥 **Export STL** prêt pour l'impression 3D (Cura, Bambu Studio, PrusaSlicer)
- ⚡ **Mode Démo local** : Testez immédiatement toutes les pièces prédéfinies même sans clé API

---

## Structure du projet

```
3D CAD/
├── app.py              ← Application Streamlit (UI studio + viewer Three.js + éditeur)
├── cad_generator.py    ← Pipeline IA → CadQuery → Propriétés B-Rep → STEP/STL
├── requirements.txt    ← Dépendances Python
├── run.bat             ← Script de lancement automatique Windows
├── .env.example        ← Template pour les variables d'environnement
├── .env                ← Clé API Gemini (optionnelle pour le mode démo)
└── output/             ← Fichiers générés (STEP, STL)
```

---

## Installation et Lancement

### Option 1 — Lancement rapide sous Windows (Recommandé)
Double-cliquez simplement sur `run.bat`. Le script configure l'environnement virtuel, installe les dépendances et lance l'application.

### Option 2 — En ligne de commande

```bash
# 1. Créer l'environnement virtuel
python -m venv .venv
.venv\Scripts\activate

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. (Optionnel) Configurer votre clé API Gemini
copy .env.example .env
# Renseigner GEMINI_API_KEY dans .env pour la génération IA libre

# 4. Lancer l'application
streamlit run app.py
```

---

## Configuration de la clé API Gemini

Pour générer **n'importe quelle pièce personnalisée** avec l'IA, obtenez une clé gratuite sur [Google AI Studio](https://aistudio.google.com/) et :
- Soit renseignez-la dans le fichier `.env` :
  ```env
  GEMINI_API_KEY=AIzaSy...
  ```
- Soit entrez-la directement dans le champ prévu dans la barre latérale de l'application.

> [!TIP]
> Si vous n'avez pas de clé API sous la main, utilisez le bouton **⚡ Mode Démo** pour générer instantanément l'un des nombreux modèles mécaniques prédéfinis.

---

## Bibliothèque de Modèles Prédéfinis

| Pièce | Spécifications géométriques |
|-------|----------------------------|
| **Plaque percée** | Plaque rectangulaire 120×80×15mm avec 4 trous de 10mm aux coins |
| **Boulon hexagonal M16** | Tête hexagonale 24mm sur plat, hauteur 10mm, tige Ø16×60mm, chanfrein 1.5mm |
| **Équerre de support** | Profil en L 80×60×8mm, largeur 50mm, congé intérieur 5mm |
| **Boîtier creux** | Boîtier 100×70×50mm, paroi 4mm, ouvert en haut, congés 3mm |
| **Bride circulaire** | Disque Ø120×15mm, alésage central Ø50mm, 4 trous Ø12 sur cercle Ø90mm |
| **Arbre épaulé étagé** | Premier étage Ø40×50mm, second étage Ø25×60mm, chanfreins 1.5mm |
| **Cylindre alésé** | Cylindre Ø50×80mm avec alésage central Ø20mm et chanfrein 2mm |

---

## Compatibilité CAO Industrielle

| Logiciel | Format | Procédure |
|----------|--------|-----------|
| **CATIA V5** | `.step` / `.stp` | Fichier → Ouvrir → Type `STEP Files (*.stp, *.step)` |
| **CATIA 3DEXPERIENCE** | `.step` | Importer via le panneau de commandes d'échange |
| **SolidWorks** | `.step` / `.stp` | Fichier → Ouvrir → Type `STEP AP203/214` (Option FeatureWorks disponible) |
| **Autodesk Fusion 360** | `.step` | Fichier → Ouvrir → Ouvrir depuis mon ordinateur |
| **FreeCAD** | `.step` | Fichier → Importer (`Ctrl + I`) |
| **Trancheurs 3D** (Cura, Bambu, Prusa) | `.stl` | Glisser-déposer direct du fichier STL |

---

## Technologies et Librairies

- **[Streamlit](https://streamlit.io)** — Interface web réactive
- **[CadQuery](https://cadquery.readthedocs.io)** — Modélisation paramétrique et noyau OpenCASCADE (OCCT)
- **[Three.js](https://threejs.org)** — Rendu 3D WebGL matériel dans le navigateur
- **[Google Gemini AI](https://ai.google.dev)** — Modèles LLM génératifs de code CAO
- **[python-dotenv](https://github.com/theskumar/python-dotenv)** — Gestion des variables d'environnement

---

## 🚀 Guide de Déploiement & Hosting

### Option A — Streamlit Community Cloud (100% Gratuit, Recommandé)
1. Créez un dépôt sur votre compte GitHub (public ou privé) et poussez le code :
   ```bash
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<votre-utilisateur>/<votre-repo>.git
   git push -u origin main
   ```
2. Rendez-vous sur [share.streamlit.io](https://share.streamlit.io/) et connectez votre compte GitHub.
3. Cliquez sur **"New app"** et sélectionnez votre dépôt.
   - **Main file path** : `app.py`
4. Ouvrez **Advanced settings** :
   - Ajoutez votre clé secrète dans la section **Secrets** :
     ```toml
     GEMINI_API_KEY = "votre_cle_api_ici"
     ```
5. Cliquez sur **Deploy!** Le fichier `packages.txt` installera automatiquement les bibliothèques système nécessaires pour CadQuery.

### Option B — Déploiement Docker (VPS, Railway, Render)
Un `Dockerfile` optimisé pour Linux Debian avec les dépendances OpenCASCADE est fourni :

```bash
# Construire et lancer le conteneur en local ou sur votre VPS
docker compose up -d --build
```
L'application sera accessible sur `http://<IP_DU_SERVEUR>:8501`.

### Option C — Hugging Face Spaces (Gratuit)
1. Créez un Space sur [Hugging Face](https://huggingface.co/spaces) avec le SDK **Streamlit** ou **Docker**.
2. Poussez les fichiers sur le dépôt Git du Space.
3. Dans **Settings > Variables and secrets**, ajoutez le secret `GEMINI_API_KEY`.

