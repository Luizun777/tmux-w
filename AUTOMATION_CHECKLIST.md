# 📋 Checklist Maestro de Automatización — tmux-w

## Diagnóstico de Rendimiento

### Estado Actual (Pre-Automatización)
- ❌ **Sin CI/CD**: No hay workflows de GitHub Actions
- ❌ **Sin linting**: Código no validado automáticamente
- ❌ **Sin cache**: Dependencies se descargan fresh en cada run
- ❌ **Sin scripts de dev**: Setup manual y lento
- ❌ **Sin pre-commit hooks**: Errores de código no detectados antes de push
- ❌ **Sin paralelización de tests**: Tests corre secuencialmente
- ⚠️ **venv grande (38MB)**: No cacheado en workflows

---

## ✅ CHECKLIST DE AUTOMATIZACIÓN

### **Tier 1: CI/CD Workflows (Prioridad Alta)**
Impacto: Detectar errores rápido, acelerar desarrollo

- [ ] **1.1** — Crear `.github/workflows/tests.yml`
  - Trigger: push, pull_request
  - Python 3.10, 3.11, 3.12
  - Cache: pip dependencies + venv
  - Parallelizar tests por archivo
  - Status badge en README

- [ ] **1.2** — Crear `.github/workflows/lint.yml`
  - ruff check (fast linter)
  - pyright/mypy para type checking
  - Fail on errors
  - Auto-comment PR con violaciones

- [ ] **1.3** — Crear `.github/workflows/build.yml`
  - Build wheel + sdist
  - Verify `setuptools` config
  - Artifact upload para releases

---

### **Tier 2: Local Development Scripts (Prioridad Alta)**
Impacto: Setup más rápido (~5 min → 30 seg), dev consistente

- [ ] **2.1** — Crear `scripts/setup.ps1`
  - Check Python version (3.10+)
  - Create/update venv
  - pip install -e . + dev deps
  - Summary: listo en 30 seg

- [ ] **2.2** — Crear `scripts/test.ps1`
  - Run pytest con opciones sensatas
  - Show coverage
  - Filter por pattern opcional

- [ ] **2.3** — Crear `scripts/lint.ps1`
  - ruff check
  - mypy (type check)
  - Report resultados

- [ ] **2.4** — Crear `scripts/dev.ps1` (maestro)
  - Orquesta setup + test + lint
  - Quick mode (solo tests) vs full mode

---

### **Tier 3: Pre-commit & Quality Gates (Prioridad Media)**
Impacto: Código limpio antes de commit, menos churn

- [ ] **3.1** — Crear `.pre-commit-config.yaml`
  - ruff format check
  - ruff lint
  - mypy (local)
  - End-of-file fixer
  - Trailing whitespace

- [ ] **3.2** — Documentar setup con `pre-commit install` en README

---

### **Tier 4: Optimizaciones de Performance (Prioridad Media)**
Impacto: Tests más rápido, workflows menos tiempo

- [ ] **4.1** — Paralelizar pytest en workflows
  - Usar `pytest-xdist`
  - Distribuir tests entre cores

- [ ] **4.2** — Split test matrix
  - Test rápidos (unit) en cada push
  - Test integración (lento) solo en PR/main
  - Artifact cache entre jobs

- [ ] **4.3** — Optimizar imports en modules
  - Lazy load `ctypes`, `msvcrt` solo donde se usan
  - Profile con `cProfile` si es necesario

---

### **Tier 5: Documentación & Onboarding (Prioridad Media)**
Impacto: Nuevos contribuidores no se pierden

- [ ] **5.1** — Crear `DEVELOPMENT.md`
  - Arquitectura rápida
  - Cómo correr tests locales
  - Cómo debuggear
  - Convenciones de código

- [ ] **5.2** — Crear `CONTRIBUTING.md`
  - Cómo hacer PR
  - Pre-commit setup
  - Tipos de cambios (fix/feat/refactor)

- [ ] **5.3** — GitHub issue templates
  - Bug report
  - Feature request
  - Standards labels (bug, enhancement, docs)

---

### **Tier 6: Automatización de Releases (Prioridad Baja)**
Impacto: Releases más rápido, menos error manual

- [ ] **6.1** — Crear `.github/workflows/release.yml`
  - Trigger: tag release (v*.*)
  - Build artifacts
  - Create GitHub Release
  - Upload a PyPI (si aplica)

- [ ] **6.2** — Auto-bump version en `pyproject.toml`
  - Script que actualiza version
  - Git tag automático
  - Changelog generator

---

## 📊 Impacto Esperado

| Métrica | Antes | Después |
|---------|-------|---------|
| Setup local | 5+ min | 30 seg |
| Catch errors | Manual review | CI automático |
| Test time | Sequential | ⚡ Parallelized |
| Dev feedback loop | Hours (manual PR) | Mins (CI check) |
| Pre-push errors | Llegaban a main | Caught by pre-commit |
| New contributor ramp | Lento, confuso | 10 min + docs |

---

## 🚀 Pasos de Implementación (Recomendado)

**Semana 1: Tier 1 + 2**
1. Crear workflows básicos (test, lint, build)
2. Crear scripts PowerShell para dev
3. Status badges en README

**Semana 2: Tier 3 + 5**
1. Pre-commit hooks
2. Dev guide + Contributing
3. GitHub issue templates

**Después: Tier 4 + 6** (tune & optimize)
1. Paralelizar tests si son lentos
2. Release automation (si aplica)

---

## 📝 Notas

- **Python 3.12**: Usar específicamente (pywinpty 2.0.13 incompatible con 3.13+)
- **Platform**: Windows-only, pero CI puede correr en windows-latest
- **Dependencies**: pywinpty (Windows-specific), pyte (cross-platform)
- **Venv size**: 38MB cacheable en GitHub Actions (60+ sec save per workflow)

---

**Creado**: 2026-06-11  
**Owner**: Luis Acosta 🍕  
**Status**: Ready to implement
