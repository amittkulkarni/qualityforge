# Quality Forge 🤖

> **AI-powered automation bot that scans Python files, proposes refactors, and creates pull requests automatically.**

---

## Features

- 🔍 **Comprehensive Analysis** – Uses **LibCST** and **pylint** for deep code-quality inspection.  
- 🤖 **AI-Powered Refactoring** – Leverages Groq’s `llama-3.1-8b-instant` model to generate intelligent code improvements.  
- 🔧 **Safe Patch Application** – Applies unified-diff patches with automatic backups and formatting preservation.  
- 📝 **Automated PR Creation** – Opens GitHub pull requests with detailed inline review comments.  
- 🧠 **Vector Memory** – Learns from past, accepted patches via **ChromaDB** for faster, smarter fixes.  
- ⚡ **High Performance** – Processes up to **10 files** per run with built-in rate limiting.

---

## Architecture

Quality Forge uses a **three-agent, CrewAI** architecture:

| Agent        | Role                                 | Key Tools                              |
|--------------|--------------------------------------|----------------------------------------|
| **Reviewer** | Detects complexity, dead code, naming issues | `ast_parser`, `pylint_runner` |
| **Refactorer** | Generates patches to fix issues     | `apply_patch`                          |
| **Git Ops**  | Creates branch, commits, pushes, opens PR | `git_tool`                             |

---

## Configuration

Create a `.env` file (or export variables):

```
# Required
GROQ_API_KEY=your_groq_api_key_here

# Optional
GITHUB_TOKEN=your_github_token_here
MAX_FILES=10
RATE_LIMIT_PER_MINUTE=30
```

---

## Development

```
# Clone and install for development
git clone https://github.com/amittkulkarni/qualityforge.git
cd qualityforge
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest

# Run quality checks
ruff check src/
black --check src/
mypy src/
```

---

## Contributing

1. **Fork** the repository.  
2. Create a feature branch:  
   ```
   git checkout -b feature/amazing-feature
   ```  
3. Commit your changes:  
   ```
   git commit -m "feat: add amazing feature"
   ```  
4. Push to your branch:  
   ```
   git push origin feature/amazing-feature
   ```  
5. Open a Pull Request.

---

## License

Quality Forge is released under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

## Summary

Quality Forge delivers end-to-end, automated code-quality improvement by combining state-of-the-art AI with robust engineering practices—complete with error handling, testing, CI/CD, and extensible tooling.