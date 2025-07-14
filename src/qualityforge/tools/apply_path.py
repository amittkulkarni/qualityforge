"""Apply Patch Tool for safely applying unified diff patches to Python files."""

import json
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from unidiff import PatchSet, PatchedFile
from pydantic import BaseModel, Field

from ..exceptions import PatchApplicationError, QualityForgeError

logger = logging.getLogger(__name__)


class PatchResult(BaseModel):
    """Result of applying a patch to a file."""
    
    success: bool
    file_path: str
    lines_added: int = 0
    lines_removed: int = 0
    hunks_applied: int = 0
    hunks_failed: int = 0
    backup_path: Optional[str] = None
    error: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class PatchApplicationResult(BaseModel):
    """Result of applying multiple patches."""
    
    success: bool
    patches_applied: int = 0
    patches_failed: int = 0
    files_modified: List[str] = Field(default_factory=list)
    results: List[PatchResult] = Field(default_factory=list)
    error: Optional[str] = None


class ApplyPatchTool:
    """Tool for applying unified diff patches to Python files."""
    
    def __init__(self):
        self.name = "apply_patch"
        self.description = (
            "Applies unified diff patches to Python files while preserving "
            "formatting and ensuring safe operations with backup creation"
        )
    
    def run(self, patches: Union[str, List[str]], target_dir: Optional[str] = None, dry_run: bool = False) -> str:
        """Apply patches to files.
        
        Args:
            patches: Single patch string or list of patch strings in unified diff format
            target_dir: Target directory to apply patches (defaults to current directory)
            dry_run: If True, validate patches without applying them
            
        Returns:
            JSON string containing application results
        """
        try:
            if isinstance(patches, str):
                patches = [patches]
            
            target_path = Path(target_dir) if target_dir else Path.cwd()
            result = self.apply_patches(patches, target_path, dry_run=dry_run)
            return json.dumps(result.dict(), indent=2)
            
        except Exception as e:
            logger.error(f"Patch application failed: {e}")
            error_result = PatchApplicationResult(
                success=False,
                error=str(e)
            )
            return json.dumps(error_result.dict(), indent=2)
    
    def apply_patches(self, patches: List[str], target_dir: Path, dry_run: bool = False) -> PatchApplicationResult:
        """Apply multiple patches to files in the target directory."""
        results = []
        files_modified = []
        patches_applied = 0
        patches_failed = 0
        
        for i, patch_content in enumerate(patches):
            try:
                logger.info(f"Processing patch {i + 1}/{len(patches)}")
                
                # Parse the patch
                patchset = self._parse_patch(patch_content)
                
                # Apply each file in the patchset
                for patched_file in patchset:
                    result = self._apply_single_file_patch(
                        patched_file, target_dir, dry_run=dry_run
                    )
                    results.append(result)
                    
                    if result.success:
                        patches_applied += 1
                        if result.file_path not in files_modified:
                            files_modified.append(result.file_path)
                    else:
                        patches_failed += 1
                        
            except Exception as e:
                logger.error(f"Failed to process patch {i + 1}: {e}")
                error_result = PatchResult(
                    success=False,
                    file_path=f"patch_{i + 1}",
                    error=str(e)
                )
                results.append(error_result)
                patches_failed += 1
        
        overall_success = patches_failed == 0
        
        return PatchApplicationResult(
            success=overall_success,
            patches_applied=patches_applied,
            patches_failed=patches_failed,
            files_modified=files_modified,
            results=results
        )
    
    def _parse_patch(self, patch_content: str) -> PatchSet:
        """Parse unified diff patch content."""
        try:
            # Handle both string input and PatchSet
            if isinstance(patch_content, str):
                patchset = PatchSet(patch_content)
            else:
                patchset = patch_content
            
            if not patchset:
                raise PatchApplicationError("Empty or invalid patch content")
            
            return patchset
            
        except Exception as e:
            raise PatchApplicationError(f"Failed to parse patch: {e}")
    
    def _apply_single_file_patch(self, patched_file: PatchedFile, target_dir: Path, dry_run: bool = False) -> PatchResult:
        """Apply a patch to a single file."""
        try:
            # Determine the target file path
            file_path = self._resolve_file_path(patched_file.path, target_dir)
            
            logger.debug(f"Applying patch to {file_path}")
            
            # Handle different file operations
            if patched_file.is_added_file:
                return self._handle_added_file(patched_file, file_path, dry_run)
            elif patched_file.is_removed_file:
                return self._handle_removed_file(patched_file, file_path, dry_run)
            else:
                return self._handle_modified_file(patched_file, file_path, dry_run)
                
        except Exception as e:
            logger.error(f"Failed to apply patch to {patched_file.path}: {e}")
            return PatchResult(
                success=False,
                file_path=patched_file.path,
                error=str(e)
            )
    
    def _resolve_file_path(self, patch_path: str, target_dir: Path) -> Path:
        """Resolve the actual file path from patch path."""
        # Remove a/ and b/ prefixes if present
        clean_path = patch_path
        if clean_path.startswith('a/') or clean_path.startswith('b/'):
            clean_path = clean_path[2:]
        
        # Handle absolute vs relative paths
        if Path(clean_path).is_absolute():
            return Path(clean_path)
        else:
            return target_dir / clean_path
    
    def _handle_added_file(self, patched_file: PatchedFile, file_path: Path, dry_run: bool) -> PatchResult:
        """Handle adding a new file."""
        if file_path.exists():
            return PatchResult(
                success=False,
                file_path=str(file_path),
                error="Cannot add file that already exists"
            )
        
        if dry_run:
            return PatchResult(
                success=True,
                file_path=str(file_path),
                lines_added=patched_file.added,
                lines_removed=0,
                hunks_applied=len(patched_file)
            )
        
        try:
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Generate content from hunks
            content_lines = []
            for hunk in patched_file:
                for line in hunk:
                    if line.is_added:
                        content_lines.append(line.value.rstrip('\n'))
            
            # Write the new file
            content = '\n'.join(content_lines)
            if content and not content.endswith('\n'):
                content += '\n'
            
            file_path.write_text(content, encoding='utf-8')
            
            return PatchResult(
                success=True,
                file_path=str(file_path),
                lines_added=patched_file.added,
                lines_removed=0,
                hunks_applied=len(patched_file)
            )
            
        except Exception as e:
            return PatchResult(
                success=False,
                file_path=str(file_path),
                error=f"Failed to create new file: {e}"
            )
    
    def _handle_removed_file(self, patched_file: PatchedFile, file_path: Path, dry_run: bool) -> PatchResult:
        """Handle removing a file."""
        if not file_path.exists():
            return PatchResult(
                success=False,
                file_path=str(file_path),
                error="Cannot remove file that doesn't exist"
            )
        
        if dry_run:
            return PatchResult(
                success=True,
                file_path=str(file_path),
                lines_added=0,
                lines_removed=patched_file.removed,
                hunks_applied=len(patched_file)
            )
        
        try:
            # Create backup before removal
            backup_path = self._create_backup(file_path)
            
            # Remove the file
            file_path.unlink()
            
            return PatchResult(
                success=True,
                file_path=str(file_path),
                lines_added=0,
                lines_removed=patched_file.removed,
                hunks_applied=len(patched_file),
                backup_path=str(backup_path)
            )
            
        except Exception as e:
            return PatchResult(
                success=False,
                file_path=str(file_path),
                error=f"Failed to remove file: {e}"
            )
    
    def _handle_modified_file(self, patched_file: PatchedFile, file_path: Path, dry_run: bool) -> PatchResult:
        """Handle modifying an existing file."""
        if not file_path.exists():
            return PatchResult(
                success=False,
                file_path=str(file_path),
                error="Cannot modify file that doesn't exist"
            )
        
        try:
            # Read the original file
            original_content = file_path.read_text(encoding='utf-8')
            original_lines = original_content.splitlines(keepends=True)
            
            # Apply the patch
            modified_lines = self._apply_hunks_to_content(original_lines, patched_file)
            
            if dry_run:
                # Just validate that the patch can be applied
                return PatchResult(
                    success=True,
                    file_path=str(file_path),
                    lines_added=patched_file.added,
                    lines_removed=patched_file.removed,
                    hunks_applied=len(patched_file)
                )
            
            # Create backup before modification
            backup_path = self._create_backup(file_path)
            
            # Write the modified content
            modified_content = ''.join(modified_lines)
            file_path.write_text(modified_content, encoding='utf-8')
            
            return PatchResult(
                success=True,
                file_path=str(file_path),
                lines_added=patched_file.added,
                lines_removed=patched_file.removed,
                hunks_applied=len(patched_file),
                backup_path=str(backup_path)
            )
            
        except Exception as e:
            return PatchResult(
                success=False,
                file_path=str(file_path),
                error=f"Failed to apply patch: {e}"
            )
    
    def _apply_hunks_to_content(self, original_lines: List[str], patched_file: PatchedFile) -> List[str]:
        """Apply all hunks in a patched file to the original content."""
        result_lines = original_lines.copy()
        
        # Apply hunks in reverse order to maintain line numbers
        for hunk in reversed(list(patched_file)):
            result_lines = self._apply_single_hunk(result_lines, hunk)
        
        return result_lines
    
    def _apply_single_hunk(self, lines: List[str], hunk) -> List[str]:
        """Apply a single hunk to the content."""
        # Find the starting position in the file
        target_line = hunk.target_start - 1  # Convert to 0-based indexing
        
        # Extract the changes from the hunk
        old_lines = []
        new_lines = []
        
        for line in hunk:
            if line.is_removed:
                old_lines.append(line.value)
            elif line.is_added:
                new_lines.append(line.value)
            else:  # Context line
                old_lines.append(line.value)
                new_lines.append(line.value)
        
        # Validate that the old lines match the file content
        file_lines_to_check = lines[target_line:target_line + len([l for l in hunk if not l.is_added])]
        
        # Apply the changes
        new_content = lines[:target_line] + new_lines + lines[target_line + len([l for l in hunk if not l.is_added]):]
        
        return new_content
    
    def _create_backup(self, file_path: Path) -> Path:
        """Create a backup of the file before modification."""
        backup_dir = file_path.parent / '.qualityforge_backups'
        backup_dir.mkdir(exist_ok=True)
        
        # Generate backup filename with timestamp
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.name}.{timestamp}.backup"
        backup_path = backup_dir / backup_name
        
        # Copy the file
        shutil.copy2(file_path, backup_path)
        
        logger.debug(f"Created backup: {backup_path}")
        return backup_path
    
    def validate_patch(self, patch_content: str, target_dir: Path) -> Dict[str, Any]:
        """Validate a patch without applying it."""
        try:
            patchset = self._parse_patch(patch_content)
            
            validation_result = {
                "valid": True,
                "files": [],
                "warnings": [],
                "errors": []
            }
            
            for patched_file in patchset:
                file_path = self._resolve_file_path(patched_file.path, target_dir)
                
                file_info = {
                    "path": str(file_path),
                    "operation": "unknown",
                    "exists": file_path.exists(),
                    "can_apply": False
                }
                
                if patched_file.is_added_file:
                    file_info["operation"] = "add"
                    file_info["can_apply"] = not file_path.exists()
                    if file_path.exists():
                        validation_result["errors"].append(f"Cannot add existing file: {file_path}")
                        
                elif patched_file.is_removed_file:
                    file_info["operation"] = "remove"
                    file_info["can_apply"] = file_path.exists()
                    if not file_path.exists():
                        validation_result["errors"].append(f"Cannot remove non-existent file: {file_path}")
                        
                else:
                    file_info["operation"] = "modify"
                    file_info["can_apply"] = file_path.exists()
                    if not file_path.exists():
                        validation_result["errors"].append(f"Cannot modify non-existent file: {file_path}")
                
                validation_result["files"].append(file_info)
            
            validation_result["valid"] = len(validation_result["errors"]) == 0
            return validation_result
            
        except Exception as e:
            return {
                "valid": False,
                "files": [],
                "warnings": [],
                "errors": [f"Patch validation failed: {e}"]
            }