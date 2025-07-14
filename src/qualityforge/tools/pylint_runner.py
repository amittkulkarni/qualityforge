"""Pylint Runner Tool for comprehensive static code analysis."""

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from io import StringIO
import sys

from pylint import lint
from pylint.reporters.text import TextReporter
from pydantic import BaseModel, Field

from ..exceptions import AnalysisError, QualityForgeError

logger = logging.getLogger(__name__)


class PylintMessage(BaseModel):
    """Represents a single pylint message."""
    
    type: str  # convention, refactor, warning, error, fatal
    module: str
    obj: str
    line: int
    column: int
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    path: str
    symbol: str
    message: str
    message_id: str
    category: str
    confidence: str = "HIGH"


class PylintStats(BaseModel):
    """Pylint analysis statistics."""
    
    convention: int = 0
    refactor: int = 0
    warning: int = 0
    error: int = 0
    fatal: int = 0
    total_issues: int = 0
    score: float = 0.0
    previous_score: Optional[float] = None
    global_note: float = 0.0


class PylintResult(BaseModel):
    """Complete pylint analysis result."""
    
    success: bool
    file_path: str
    messages: List[PylintMessage] = Field(default_factory=list)
    stats: Optional[PylintStats] = None
    raw_output: Optional[str] = None
    error: Optional[str] = None
    exit_code: int = 0


class WritableObject:
    """Helper class to capture pylint output."""
    
    def __init__(self):
        self.content = []
    
    def write(self, st):
        """Write string to content list."""
        self.content.append(st)
    
    def read(self):
        """Read all content."""
        return self.content


class PylintRunnerTool:
    """Tool for running pylint analysis on Python files."""
    
    def __init__(self):
        self.name = "pylint_runner"
        self.description = (
            "Runs comprehensive pylint static code analysis and returns "
            "detailed issues, warnings, and quality metrics"
        )
        
        # Default pylint configuration
        self.default_args = [
            "--reports=no",  # Disable reports section
            "--score=yes",   # Include score
            "--msg-template={path}:{line}:{column}: {msg_id}: {msg} ({symbol})",
            "--output-format=json",  # JSON output for easier parsing
            "--disable=missing-docstring,too-few-public-methods",  # Disable some noisy checks
            "--max-line-length=88",  # Match Black's line length
            "--good-names=i,j,k,ex,Run,_,fd,fp",  # Allow common short names
        ]
    
    def run(self, file_path: Union[str, Path], config_file: Optional[str] = None) -> str:
        """Run pylint analysis on a Python file.
        
        Args:
            file_path: Path to the Python file to analyze
            config_file: Optional path to pylint configuration file
            
        Returns:
            JSON string containing analysis results
        """
        try:
            result = self.analyze_file(Path(file_path), config_file)
            return json.dumps(result.dict(), indent=2)
        except Exception as e:
            logger.error(f"Pylint analysis failed for {file_path}: {e}")
            error_result = PylintResult(
                success=False,
                file_path=str(file_path),
                error=str(e)
            )
            return json.dumps(error_result.dict(), indent=2)
    
    def analyze_file(self, file_path: Path, config_file: Optional[str] = None) -> PylintResult:
        """Analyze a single Python file with pylint."""
        if not file_path.exists():
            return PylintResult(
                success=False,
                file_path=str(file_path),
                error="File does not exist"
            )
        
        if not file_path.suffix == '.py':
            return PylintResult(
                success=False,
                file_path=str(file_path),
                error="File is not a Python file"
            )
        
        try:
            # Prepare arguments
            args = self.default_args.copy()
            
            if config_file and Path(config_file).exists():
                args.extend(["--rcfile", config_file])
            
            args.append(str(file_path))
            
            # Method 1: Try using pylint programmatically
            try:
                result = self._run_pylint_programmatic(args, file_path)
                if result.success:
                    return result
            except Exception as e:
                logger.warning(f"Programmatic pylint failed, trying subprocess: {e}")
            
            # Method 2: Fallback to subprocess
            return self._run_pylint_subprocess(args, file_path)
            
        except Exception as e:
            logger.error(f"Pylint analysis failed for {file_path}: {e}")
            return PylintResult(
                success=False,
                file_path=str(file_path),
                error=str(e)
            )
    
    def _run_pylint_programmatic(self, args: List[str], file_path: Path) -> PylintResult:
        """Run pylint programmatically using the Python API."""
        # Capture stdout and stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        
        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            
            # Create a custom reporter to capture JSON output
            output_capture = WritableObject()
            reporter = TextReporter(output_capture)
            
            # Run pylint
            try:
                exit_code = lint.Run(args, reporter=reporter, exit=False).linter.msg_status
            except SystemExit as e:
                exit_code = e.code
            
            # Get output
            raw_output = ''.join(output_capture.read())
            stderr_output = stderr_capture.getvalue()
            
            # Parse the output
            messages, stats = self._parse_pylint_output(raw_output, file_path)
            
            return PylintResult(
                success=True,
                file_path=str(file_path),
                messages=messages,
                stats=stats,
                raw_output=raw_output,
                exit_code=exit_code
            )
            
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
    
    def _run_pylint_subprocess(self, args: List[str], file_path: Path) -> PylintResult:
        """Run pylint using subprocess as fallback."""
        try:
            # Prepare command
            cmd = ["python", "-m", "pylint"] + args
            
            # Run subprocess
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,  # 60 second timeout
                cwd=file_path.parent
            )
            
            # Parse output
            messages, stats = self._parse_pylint_output(result.stdout, file_path)
            
            return PylintResult(
                success=True,
                file_path=str(file_path),
                messages=messages,
                stats=stats,
                raw_output=result.stdout,
                exit_code=result.returncode
            )
            
        except subprocess.TimeoutExpired:
            return PylintResult(
                success=False,
                file_path=str(file_path),
                error="Pylint analysis timed out"
            )
        except subprocess.CalledProcessError as e:
            return PylintResult(
                success=False,
                file_path=str(file_path),
                error=f"Pylint subprocess failed: {e}",
                exit_code=e.returncode
            )
    
    def _parse_pylint_output(self, output: str, file_path: Path) -> tuple[List[PylintMessage], PylintStats]:
        """Parse pylint output and extract messages and statistics."""
        messages = []
        stats = PylintStats()
        
        if not output.strip():
            return messages, stats
        
        try:
            # Try to parse as JSON first
            if output.strip().startswith('['):
                json_data = json.loads(output)
                for item in json_data:
                    message = PylintMessage(
                        type=item.get('type', 'unknown'),
                        module=item.get('module', ''),
                        obj=item.get('obj', ''),
                        line=item.get('line', 0),
                        column=item.get('column', 0),
                        end_line=item.get('endLine'),
                        end_column=item.get('endColumn'),
                        path=item.get('path', str(file_path)),
                        symbol=item.get('symbol', ''),
                        message=item.get('message', ''),
                        message_id=item.get('message-id', ''),
                        category=self._get_category_from_type(item.get('type', '')),
                        confidence=item.get('confidence', 'HIGH')
                    )
                    messages.append(message)
            else:
                # Parse text output
                messages = self._parse_text_output(output, file_path)
            
            # Calculate statistics
            stats = self._calculate_stats(messages, output)
            
        except json.JSONDecodeError:
            # Fallback to text parsing
            messages = self._parse_text_output(output, file_path)
            stats = self._calculate_stats(messages, output)
        except Exception as e:
            logger.warning(f"Failed to parse pylint output: {e}")
        
        return messages, stats
    
    def _parse_text_output(self, output: str, file_path: Path) -> List[PylintMessage]:
        """Parse text format pylint output."""
        messages = []
        
        for line in output.split('\n'):
            line = line.strip()
            if not line or line.startswith('*') or line.startswith('-'):
                continue
            
            # Parse line format: path:line:column: msg_id: message (symbol)
            try:
                if ':' in line:
                    parts = line.split(':')
                    if len(parts) >= 4:
                        path = parts[0]
                        line_num = int(parts[1])
                        column = int(parts[2])
                        
                        # Extract message and symbol
                        rest = ':'.join(parts[3:]).strip()
                        if ' (' in rest and rest.endswith(')'):
                            message_part, symbol_part = rest.rsplit(' (', 1)
                            symbol = symbol_part.rstrip(')')
                            
                            # Extract message ID
                            if message_part.startswith(' '):
                                message_part = message_part[1:]
                            
                            if ' ' in message_part:
                                msg_id, message = message_part.split(' ', 1)
                            else:
                                msg_id = message_part
                                message = ""
                            
                            # Determine type from message ID
                            msg_type = self._get_type_from_message_id(msg_id)
                            
                            pylint_message = PylintMessage(
                                type=msg_type,
                                module='',
                                obj='',
                                line=line_num,
                                column=column,
                                path=path,
                                symbol=symbol,
                                message=message,
                                message_id=msg_id,
                                category=self._get_category_from_type(msg_type)
                            )
                            messages.append(pylint_message)
            except (ValueError, IndexError) as e:
                logger.debug(f"Could not parse pylint line: {line} - {e}")
                continue
        
        return messages
    
    def _get_type_from_message_id(self, msg_id: str) -> str:
        """Get message type from message ID."""
        if not msg_id:
            return 'unknown'
        
        first_char = msg_id[0].upper()
        type_map = {
            'C': 'convention',
            'R': 'refactor',
            'W': 'warning',
            'E': 'error',
            'F': 'fatal'
        }
        return type_map.get(first_char, 'unknown')
    
    def _get_category_from_type(self, msg_type: str) -> str:
        """Get category from message type."""
        category_map = {
            'convention': 'style',
            'refactor': 'design',
            'warning': 'warning',
            'error': 'error',
            'fatal': 'error'
        }
        return category_map.get(msg_type, 'unknown')
    
    def _calculate_stats(self, messages: List[PylintMessage], output: str) -> PylintStats:
        """Calculate statistics from messages and output."""
        stats = PylintStats()
        
        # Count message types
        for message in messages:
            if message.type == 'convention':
                stats.convention += 1
            elif message.type == 'refactor':
                stats.refactor += 1
            elif message.type == 'warning':
                stats.warning += 1
            elif message.type == 'error':
                stats.error += 1
            elif message.type == 'fatal':
                stats.fatal += 1
        
        stats.total_issues = len(messages)
        
        # Try to extract score from output
        try:
            for line in output.split('\n'):
                if 'Your code has been rated at' in line:
                    # Extract score like "Your code has been rated at 7.50/10"
                    score_part = line.split('Your code has been rated at')[1]
                    if '/' in score_part:
                        score_str = score_part.split('/')[0].strip()
                        stats.score = float(score_str)
                        stats.global_note = stats.score
                        break
        except (ValueError, IndexError):
            # Calculate approximate score based on issues
            # Simplified scoring: start with 10, subtract for each issue type
            score = 10.0
            score -= stats.fatal * 2.0
            score -= stats.error * 1.0
            score -= stats.warning * 0.5
            score -= stats.refactor * 0.25
            score -= stats.convention * 0.1
            stats.score = max(0.0, score)
            stats.global_note = stats.score
        
        return stats
    
    def analyze_multiple_files(self, file_paths: List[Path], config_file: Optional[str] = None) -> List[PylintResult]:
        """Analyze multiple Python files."""
        results = []
        for file_path in file_paths:
            result = self.analyze_file(file_path, config_file)
            results.append(result)
        return results