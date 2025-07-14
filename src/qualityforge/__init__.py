"""Quality Forge - Production-ready quality-automation bot powered by CrewAI and Groq.

Quality Forge is a multi-agent system that scans Python files, proposes refactors,
adds inline PR comments, and opens pull requests automatically.
"""

__version__ = "0.1.0"
__author__ = "Quality Forge Team"
__email__ = "team@qualityforge.dev"

from .main import run

__all__ = ["run", "__version__"]