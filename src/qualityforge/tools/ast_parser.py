"""AST Parser Tool for analyzing Python code structure and metrics."""

import ast
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

import libcst as cst
from libcst import metadata
from pydantic import BaseModel, Field

from ..exceptions import AnalysisError, QualityForgeError

logger = logging.getLogger(__name__)


class CodeMetrics(BaseModel):
    """Code metrics extracted from AST analysis."""
    
    file_path: str
    lines_of_code: int
    blank_lines: int
    comment_lines: int
    cyclomatic_complexity: float
    cognitive_complexity: float
    maintainability_index: float
    classes: int
    functions: int
    methods: int
    imports: int
    variables: int
    constants: int
    code_to_comment_ratio: float
    average_function_length: float
    max_function_length: int
    nested_depth: int


class CodeIssue(BaseModel):
    """Represents a code quality issue found during AST analysis."""
    
    type: str
    severity: str = Field(..., regex="^(critical|high|medium|low)$")
    line_number: int
    column: int = 0
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    message: str
    rule: str
    suggestion: Optional[str] = None
    context: Optional[str] = None


class ASTAnalysisResult(BaseModel):
    """Complete AST analysis result for a Python file."""
    
    success: bool
    file_path: str
    metrics: Optional[CodeMetrics] = None
    issues: List[CodeIssue] = Field(default_factory=list)
    ast_json: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ComplexityAnalyzer(cst.CSTVisitor):
    """Visitor to calculate cyclomatic and cognitive complexity."""
    
    METADATA_DEPENDENCIES = (metadata.PositionProvider,)
    
    def __init__(self):
        self.cyclomatic_complexity = 1  # Start with 1 for the main path
        self.cognitive_complexity = 0
        self.function_complexities = []
        self.current_function_complexity = 0
        self.nesting_level = 0
        self.function_lengths = []
        self.current_function_lines = 0
        self.max_depth = 0
        self.current_depth = 0
        
    def visit_FunctionDef(self, node: cst.FunctionDef) -> Optional[bool]:
        """Visit function definition."""
        self.current_function_complexity = 1
        self.current_function_lines = 0
        self.nesting_level += 1
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)
        return True
    
    def leave_FunctionDef(self, node: cst.FunctionDef) -> None:
        """Leave function definition."""
        self.function_complexities.append(self.current_function_complexity)
        self.function_lengths.append(self.current_function_lines)
        self.nesting_level -= 1
        self.current_depth -= 1
    
    def visit_If(self, node: cst.If) -> Optional[bool]:
        """Visit if statement."""
        self.cyclomatic_complexity += 1
        self.current_function_complexity += 1
        self.cognitive_complexity += (1 + self.nesting_level)
        return True
    
    def visit_While(self, node: cst.While) -> Optional[bool]:
        """Visit while loop."""
        self.cyclomatic_complexity += 1
        self.current_function_complexity += 1
        self.cognitive_complexity += (1 + self.nesting_level)
        self.nesting_level += 1
        return True
    
    def leave_While(self, node: cst.While) -> None:
        """Leave while loop."""
        self.nesting_level -= 1
    
    def visit_For(self, node: cst.For) -> Optional[bool]:
        """Visit for loop."""
        self.cyclomatic_complexity += 1
        self.current_function_complexity += 1
        self.cognitive_complexity += (1 + self.nesting_level)
        self.nesting_level += 1
        return True
    
    def leave_For(self, node: cst.For) -> None:
        """Leave for loop."""
        self.nesting_level -= 1
    
    def visit_Try(self, node: cst.Try) -> Optional[bool]:
        """Visit try statement."""
        # Each except clause adds complexity
        self.cyclomatic_complexity += len(node.handlers)
        self.current_function_complexity += len(node.handlers)
        self.cognitive_complexity += len(node.handlers)
        return True


class ASTParserTool:
    """Tool for parsing Python code and extracting AST metrics."""
    
    def __init__(self):
        self.name = "ast_parser"
        self.description = (
            "Parses Python source code and extracts detailed AST metrics including "
            "complexity, structure, and quality indicators"
        )
    
    def run(self, file_path: Union[str, Path], return_ast: bool = False) -> str:
        """Parse a Python file and return analysis results as JSON.
        
        Args:
            file_path: Path to the Python file to analyze
            return_ast: Whether to include AST JSON in the result
            
        Returns:
            JSON string containing analysis results
        """
        try:
            result = self.analyze_file(Path(file_path), return_ast=return_ast)
            return json.dumps(result.dict(), indent=2)
        except Exception as e:
            logger.error(f"AST parsing failed for {file_path}: {e}")
            error_result = ASTAnalysisResult(
                success=False,
                file_path=str(file_path),
                error=str(e)
            )
            return json.dumps(error_result.dict(), indent=2)
    
    def analyze_file(self, file_path: Path, return_ast: bool = False) -> ASTAnalysisResult:
        """Analyze a single Python file."""
        try:
            # Read the file
            source_code = file_path.read_text(encoding='utf-8')
            
            # Parse with LibCST for detailed analysis
            cst_tree = cst.parse_expression(source_code) if self._is_expression(source_code) else cst.parse_module(source_code)
            
            # Create metadata wrapper for position tracking
            wrapper = metadata.MetadataWrapper(cst_tree)
            
            # Analyze complexity
            complexity_analyzer = ComplexityAnalyzer()
            wrapper.visit(complexity_analyzer)
            
            # Parse with standard AST for additional metrics
            ast_tree = ast.parse(source_code, filename=str(file_path))
            
            # Extract metrics
            metrics = self._extract_metrics(
                file_path, source_code, ast_tree, complexity_analyzer
            )
            
            # Find issues
            issues = self._find_issues(source_code, ast_tree, complexity_analyzer)
            
            # Convert AST to JSON if requested
            ast_json = None
            if return_ast:
                ast_json = self._ast_to_dict(ast_tree)
            
            return ASTAnalysisResult(
                success=True,
                file_path=str(file_path),
                metrics=metrics,
                issues=issues,
                ast_json=ast_json
            )
            
        except SyntaxError as e:
            logger.error(f"Syntax error in {file_path}: {e}")
            return ASTAnalysisResult(
                success=False,
                file_path=str(file_path),
                error=f"Syntax error: {e}"
            )
        except Exception as e:
            logger.error(f"Analysis failed for {file_path}: {e}")
            return ASTAnalysisResult(
                success=False,
                file_path=str(file_path),
                error=str(e)
            )
    
    def _is_expression(self, source_code: str) -> bool:
        """Check if source code is a single expression."""
        try:
            ast.parse(source_code, mode='eval')
            return True
        except SyntaxError:
            return False
    
    def _extract_metrics(
        self,
        file_path: Path,
        source_code: str,
        ast_tree: ast.AST,
        complexity_analyzer: ComplexityAnalyzer
    ) -> CodeMetrics:
        """Extract comprehensive code metrics."""
        lines = source_code.split('\n')
        
        # Count different types of lines
        code_lines = 0
        comment_lines = 0
        blank_lines = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                blank_lines += 1
            elif stripped.startswith('#'):
                comment_lines += 1
            else:
                code_lines += 1
                # Check for inline comments
                if '#' in line:
                    comment_lines += 0.5  # Partial credit for inline comments
        
        # Count AST nodes
        node_counts = self._count_ast_nodes(ast_tree)
        
        # Calculate derived metrics
        total_lines = len(lines)
        code_to_comment_ratio = code_lines / max(comment_lines, 1)
        
        # Calculate maintainability index (simplified version)
        # MI = max(0, 171 - 5.2 * ln(HV) - 0.23 * CC - 16.2 * ln(LOC))
        # Where HV = Halstead Volume, CC = Cyclomatic Complexity, LOC = Lines of Code
        # Simplified version without Halstead metrics
        import math
        maintainability_index = max(
            0,
            171 - 0.23 * complexity_analyzer.cyclomatic_complexity - 16.2 * math.log(max(code_lines, 1))
        )
        
        # Function length metrics
        avg_function_length = (
            sum(complexity_analyzer.function_lengths) / max(len(complexity_analyzer.function_lengths), 1)
        )
        max_function_length = max(complexity_analyzer.function_lengths) if complexity_analyzer.function_lengths else 0
        
        return CodeMetrics(
            file_path=str(file_path),
            lines_of_code=code_lines,
            blank_lines=blank_lines,
            comment_lines=int(comment_lines),
            cyclomatic_complexity=complexity_analyzer.cyclomatic_complexity,
            cognitive_complexity=complexity_analyzer.cognitive_complexity,
            maintainability_index=maintainability_index,
            classes=node_counts.get('ClassDef', 0),
            functions=node_counts.get('FunctionDef', 0),
            methods=node_counts.get('AsyncFunctionDef', 0),
            imports=node_counts.get('Import', 0) + node_counts.get('ImportFrom', 0),
            variables=node_counts.get('Name', 0),
            constants=node_counts.get('Constant', 0),
            code_to_comment_ratio=code_to_comment_ratio,
            average_function_length=avg_function_length,
            max_function_length=max_function_length,
            nested_depth=complexity_analyzer.max_depth,
        )
    
    def _count_ast_nodes(self, tree: ast.AST) -> Dict[str, int]:
        """Count different types of AST nodes."""
        counts = {}
        for node in ast.walk(tree):
            node_type = type(node).__name__
            counts[node_type] = counts.get(node_type, 0) + 1
        return counts
    
    def _find_issues(
        self,
        source_code: str,
        ast_tree: ast.AST,
        complexity_analyzer: ComplexityAnalyzer
    ) -> List[CodeIssue]:
        """Find code quality issues."""
        issues = []
        
        # Check for high complexity
        if complexity_analyzer.cyclomatic_complexity > 15:
            issues.append(CodeIssue(
                type="complexity",
                severity="high",
                line_number=1,
                message=f"High cyclomatic complexity: {complexity_analyzer.cyclomatic_complexity}",
                rule="C901",
                suggestion="Consider breaking down complex functions into smaller ones"
            ))
        
        # Check for long functions
        for i, length in enumerate(complexity_analyzer.function_lengths):
            if length > 50:
                issues.append(CodeIssue(
                    type="function_length",
                    severity="medium",
                    line_number=1,  # Would need position tracking for exact line
                    message=f"Function is too long: {length} lines",
                    rule="R0915",
                    suggestion="Consider breaking this function into smaller functions"
                ))
        
        # Check for deeply nested code
        if complexity_analyzer.max_depth > 5:
            issues.append(CodeIssue(
                type="nesting",
                severity="medium",
                line_number=1,
                message=f"Code is deeply nested: {complexity_analyzer.max_depth} levels",
                rule="R1702",
                suggestion="Consider refactoring to reduce nesting levels"
            ))
        
        # Check naming conventions
        for node in ast.walk(ast_tree):
            if isinstance(node, ast.FunctionDef):
                if not node.name.islower() or '__' in node.name:
                    issues.append(CodeIssue(
                        type="naming",
                        severity="low",
                        line_number=getattr(node, 'lineno', 1),
                        message=f"Function name '{node.name}' doesn't follow snake_case convention",
                        rule="C0103",
                        suggestion="Use snake_case for function names"
                    ))
            
            elif isinstance(node, ast.ClassDef):
                if not node.name[0].isupper():
                    issues.append(CodeIssue(
                        type="naming",
                        severity="low",
                        line_number=getattr(node, 'lineno', 1),
                        message=f"Class name '{node.name}' doesn't follow PascalCase convention",
                        rule="C0103",
                        suggestion="Use PascalCase for class names"
                    ))
        
        return issues
    
    def _ast_to_dict(self, node: ast.AST) -> Dict[str, Any]:
        """Convert AST node to dictionary representation."""
        if isinstance(node, ast.AST):
            result = {'type': type(node).__name__}
            for field, value in ast.iter_fields(node):
                if isinstance(value, list):
                    result[field] = [self._ast_to_dict(item) for item in value]
                elif isinstance(value, ast.AST):
                    result[field] = self._ast_to_dict(value)
                else:
                    result[field] = value
            return result
        else:
            return repr(node)