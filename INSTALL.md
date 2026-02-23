# 📦 Full SEO Automation — Step-by-Step Installation Guide

> Complete guide to install and run the Full SEO Automation platform on your machine.

---

## 📋 Prerequisites

Before you begin, make sure you have:

| Requirement | Minimum Version | Check Command |
|-------------|:--------------:|---------------|
| Python | 3.10+ | `python3 --version` |
| pip | Latest | `pip --version` |
| Git | Any | `git --version` |
| Operating System | Linux, macOS, or Windows (WSL recommended) | — |
| RAM | 4 GB minimum (8 GB recommended) | — |
| Disk Space | 2 GB free | — |

---

## 🚀 Installation Steps

### Step 1: Download the Project

**Option A: Clone from GitHub**
```bash
git clone https://github.com/loydz21/Full-SEO-Automation.git
cd Full-SEO-Automation
```

**Option B: Download ZIP**
1. Go to https://github.com/loydz21/Full-SEO-Automation
2. Click the green **"Code"** button
3. Click **"Download ZIP"**
4. Extract the ZIP file
5. Open terminal and navigate to the extracted folder:
```bash
cd Full-SEO-Automation
```

---

### Step 2: Create a Python Virtual Environment

A virtual environment keeps the project's dependencies separate from your system Python.

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (Command Prompt):**
```cmd
python -m venv venv
venv\Scripts\activate
```

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

> ✅ You should see `(venv)` at the beginning of your terminal prompt.

---

### Step 3: Upgrade pip

```bash
pip install --upgrade pip setuptools wheel
```

---

### Step 4: Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs all required packages (~40 packages). It may take 2-5 minutes.

> ⚠️ **If you get errors**, try installing problem packages individually:
> ```bash
> pip install aiohttp beautifulsoup4 openai streamlit typer rich
> pip install sqlalchemy apscheduler playwright feedparser
> pip install spacy textstat scikit-learn plotly pandas
> ```

---

### Step 5: Install Playwright Browser (for Web Scraping)

Playwright is used for SERP scraping and site crawling.

```bash
playwright install chromium
```

> This downloads the Chromium browser (~150 MB). Only needs to be done once.

**Linux users** — you may also need system dependencies:
```bash
playwright install-deps chromium
```

---

### Step 6: Download SpaCy Language Model (for NLP)

```bash
python -m spacy download en_core_web_sm
```

---

### Step 7: Create Required Directories

```bash
mkdir -p data/cache data/exports data/templates docs
```

---

### Step 8: Configure Your API Keys

**8a. Copy the example environment file:**
```bash
cp .env.example .env
```

**8b. Open `.env` in a text editor:**
```bash
nano .env
```
Or use any text editor (VS Code, Notepad++, vim, etc.)

**8c. Add your API keys:**

At minimum, you need ONE of these AI keys:

```env
# REQUIRED — At least one AI key
OPENAI_API_KEY=sk-your-openai-key-here

# OPTIONAL — Free backup AI (recommended)
GEMINI_API_KEY=your-gemini-key-here
```

**Where to get API keys:**

| API Key | Where to Get It | Cost | Required? |
|---------|-----------------|:----:|:---------:|
| **OpenAI** | https://platform.openai.com/api-keys | ~$30-50/mo | ✅ Yes |
| **Gemini** | https://aistudio.google.com/apikey | Free tier | ❌ Optional |
| **Google Search Console** | https://search.google.com/search-console | Free | ❌ Optional |
| **Google PageSpeed** | https://developers.google.com/speed/docs/insights/v5/get-started | Free | ❌ Optional |
| **SerpAPI** | https://serpapi.com/ | Free 100/mo | ❌ Optional |

> 💡 **Tip**: You can start with just the OpenAI key and add others later through the Settings page.

**8d. Save and close the file** (in nano: `Ctrl+X`, then `Y`, then `Enter`)

---

### Step 9: Initialize the Database

```bash
python -c "from src.database import init_db; init_db()"
```

> ✅ This creates the SQLite database with all 25+ tables.

---

### Step 10: Verify the Installation

**10a. Run the syntax check (all 85 Python files):**
```bash
python -c "
import ast, os
errors = 0
total = 0
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('venv', '__pycache__', '.git')]
    for f in files:
        if f.endswith('.py'):
            total += 1
            try:
                ast.parse(open(os.path.join(root, f)).read())
            except SyntaxError as e:
                print(f'ERROR: {os.path.join(root, f)}: Line {e.lineno}')
                errors += 1
print(f'Checked {total} files — {errors} errors')
"
```

> ✅ Expected: `Checked 85 files — 0 errors`

**10b. Run the test suite:**
```bash
pytest tests/ -v --tb=short
```

> ✅ Expected: `90 passed, 10 skipped`

**10c. Check CLI works:**
```bash
python -m src.cli status
```

---

### Step 11: Launch the Dashboard! 🚀

```bash
streamlit run dashboard/app.py
```

The dashboard will open automatically in your browser at:

> 🌐 **http://localhost:8501**

You should see the **Full SEO Automation** dashboard with:
- 🏠 Overview page with module score cards
- 📍 11 navigation pages in the sidebar
- ⚙️ Settings page to manage API keys

---

## 🎯 First Things to Do After Installation

### 1. Configure API Keys in the Dashboard
1. Click **⚙️ Settings & API Keys** in the sidebar
2. Enter your OpenAI API key
3. Click **🧪 Test Connection** to verify
4. Click **💾 Save All Settings**

### 2. Run Your First SEO Audit
1. Click **🔧 Technical Audit** in the sidebar
2. Enter your website URL
3. Click **🔍 Run Audit**
4. Review the results across all tabs

### 3. Try the Full Pipeline (CLI)
```bash
python -m src.cli full example.com --keywords "seo tools,keyword research"
```

---

## 🔧 Alternative: Automated Setup Script

If you prefer a one-command setup:

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

This script automatically:
1. ✅ Checks Python version
2. ✅ Creates virtual environment
3. ✅ Installs all dependencies
4. ✅ Installs Playwright + Chromium
5. ✅ Creates data directories
6. ✅ Copies `.env.example` → `.env`
7. ✅ Initializes database
8. ✅ Validates all Python files

---

## ❓ Troubleshooting

### "ModuleNotFoundError: No module named 'xxx'"
Make sure your virtual environment is activated:
```bash
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
```
Then reinstall:
```bash
pip install -r requirements.txt
```

### "Playwright browsers not found"
```bash
playwright install chromium
```

### "Permission denied" on setup.sh
```bash
chmod +x scripts/setup.sh
```

### "sqlite3.OperationalError: database is locked"
Make sure only one instance of the app is running.

### "OpenAI API Error: 401 Unauthorized"
Check your API key in `.env` file or Settings page.

### Port 8501 already in use
```bash
streamlit run dashboard/app.py --server.port 8502
```

### Windows-specific Issues
- Use WSL2 (Windows Subsystem for Linux) for best compatibility
- Or use PowerShell with admin privileges
- Replace `python3` with `python` in all commands

### Mac Apple Silicon (M1/M2/M3) Issues
Some packages may need Rosetta:
```bash
arch -x86_64 pip install -r requirements.txt
```

---

## 📞 Getting Help

1. Check the `README.md` for full documentation
2. Check `API_BUDGET.md` for cost details
3. Check `PLAN.md` for architecture details
4. Run `python -m src.cli status` for system diagnostics

---

## 🔄 Updating the Project

To update to the latest version:

```bash
git pull origin main
pip install -r requirements.txt
python -c "from src.database import init_db; init_db()"
```

---

**✅ Installation Complete! You're ready to automate your SEO. 🚀**
