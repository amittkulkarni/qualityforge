"""Git Tool for managing repository operations and GitHub API interactions."""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

import git
import requests
from pydantic import BaseModel, Field

from ..exceptions import GitOperationError, NetworkError, QualityForgeError
from ..settings import settings

logger = logging.getLogger(__name__)


class GitOperationResult(BaseModel):
    """Result of a git operation."""
    
    success: bool
    operation: str
    result: Optional[str] = None
    error: Optional[str] = None
    commit_hash: Optional[str] = None
    branch_name: Optional[str] = None


class PullRequestResult(BaseModel):
    """Result of creating a pull request."""
    
    success: bool
    url: Optional[str] = None
    number: Optional[int] = None
    title: Optional[str] = None
    error: Optional[str] = None


class GitTool:
    """Tool for git operations and GitHub API interactions."""
    
    def __init__(self):
        self.name = "git_tool"
        self.description = (
            "Manages git operations including branch creation, commits, "
            "and GitHub pull request creation with inline comments"
        )
    
    def run(self, operation: str, **kwargs) -> str:
        """Execute git operations.
        
        Args:
            operation: Type of operation (create_branch, commit, push, create_pr)
            **kwargs: Operation-specific arguments
            
        Returns:
            JSON string containing operation results
        """
        try:
            if operation == "create_branch":
                result = self.create_branch(kwargs.get("repo_path"), kwargs.get("branch_name"))
            elif operation == "commit":
                result = self.commit_changes(
                    kwargs.get("repo_path"), 
                    kwargs.get("message"),
                    kwargs.get("files", [])
                )
            elif operation == "push":
                result = self.push_branch(kwargs.get("repo_path"), kwargs.get("branch_name"))
            elif operation == "create_pr":
                result = self.create_pull_request(
                    kwargs.get("repo_path"),
                    kwargs.get("title"),
                    kwargs.get("body"),
                    kwargs.get("head_branch"),
                    kwargs.get("base_branch", "main"),
                    kwargs.get("inline_comments", [])
                )
            else:
                result = GitOperationResult(
                    success=False,
                    operation=operation,
                    error=f"Unknown operation: {operation}"
                )
            
            return json.dumps(result.dict(), indent=2)
            
        except Exception as e:
            logger.error(f"Git operation '{operation}' failed: {e}")
            error_result = GitOperationResult(
                success=False,
                operation=operation,
                error=str(e)
            )
            return json.dumps(error_result.dict(), indent=2)
    
    def create_branch(self, repo_path: Union[str, Path], branch_name: Optional[str] = None) -> GitOperationResult:
        """Create a new git branch."""
        try:
            repo = git.Repo(repo_path)
            
            if branch_name is None:
                branch_name = settings.get_branch_name()
            
            # Ensure we're on the main branch
            if repo.active_branch.name != "main":
                try:
                    repo.git.checkout("main")
                except git.GitCommandError:
                    repo.git.checkout("master")
            
            # Create and checkout new branch
            new_branch = repo.create_head(branch_name)
            new_branch.checkout()
            
            return GitOperationResult(
                success=True,
                operation="create_branch",
                result=f"Created and switched to branch: {branch_name}",
                branch_name=branch_name
            )
            
        except Exception as e:
            raise GitOperationError(f"Failed to create branch: {e}")
    
    def commit_changes(self, repo_path: Union[str, Path], message: str, files: List[str] = None) -> GitOperationResult:
        """Commit changes to the repository."""
        try:
            repo = git.Repo(repo_path)
            
            # Stage files
            if files:
                for file_path in files:
                    repo.git.add(file_path)
            else:
                repo.git.add(A=True)  # Stage all changes
            
            # Check if there are changes to commit
            if not repo.is_dirty(staged=True):
                return GitOperationResult(
                    success=False,
                    operation="commit",
                    error="No changes to commit"
                )
            
            # Commit changes
            commit = repo.index.commit(message)
            
            return GitOperationResult(
                success=True,
                operation="commit",
                result=f"Committed changes: {message}",
                commit_hash=commit.hexsha
            )
            
        except Exception as e:
            raise GitOperationError(f"Failed to commit changes: {e}")
    
    def push_branch(self, repo_path: Union[str, Path], branch_name: str) -> GitOperationResult:
        """Push branch to remote repository."""
        try:
            repo = git.Repo(repo_path)
            
            # Get the origin remote
            origin = repo.remote("origin")
            
            # Push the branch
            push_info = origin.push(branch_name)
            
            return GitOperationResult(
                success=True,
                operation="push",
                result=f"Pushed branch {branch_name} to origin",
                branch_name=branch_name
            )
            
        except Exception as e:
            raise GitOperationError(f"Failed to push branch: {e}")
    
    def create_pull_request(
        self,
        repo_path: Union[str, Path],
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
        inline_comments: List[Dict[str, Any]] = None
    ) -> PullRequestResult:
        """Create a pull request on GitHub."""
        try:
            if not settings.github_token:
                raise GitOperationError("GitHub token not configured")
            
            # Extract repository info
            repo = git.Repo(repo_path)
            remote_url = repo.remote("origin").url
            
            # Parse GitHub repository from remote URL
            if "github.com" not in remote_url:
                raise GitOperationError("Repository is not hosted on GitHub")
            
            # Extract owner and repo name
            if remote_url.startswith("https://"):
                parts = remote_url.replace("https://github.com/", "").replace(".git", "").split("/")
            else:
                parts = remote_url.replace("git@github.com:", "").replace(".git", "").split("/")
            
            if len(parts) != 2:
                raise GitOperationError("Could not parse repository information")
            
            owner, repo_name = parts
            
            # Create pull request
            pr_data = {
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch,
                "draft": False
            }
            
            headers = {
                "Authorization": f"token {settings.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                f"https://api.github.com/repos/{owner}/{repo_name}/pulls",
                json=pr_data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 201:
                pr_info = response.json()
                pr_number = pr_info["number"]
                pr_url = pr_info["html_url"]
                
                # Add inline comments if provided
                if inline_comments:
                    self._add_inline_comments(owner, repo_name, pr_number, inline_comments)
                
                return PullRequestResult(
                    success=True,
                    url=pr_url,
                    number=pr_number,
                    title=title
                )
            else:
                raise NetworkError(f"GitHub API error: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Failed to create pull request: {e}")
            return PullRequestResult(
                success=False,
                error=str(e)
            )
    
    def _add_inline_comments(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        comments: List[Dict[str, Any]]
    ) -> None:
        """Add inline comments to a pull request."""
        headers = {
            "Authorization": f"token {settings.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }
        
        for comment in comments:
            comment_data = {
                "body": comment["body"],
                "path": comment["path"],
                "line": comment["line"],
                "side": "RIGHT"  # Comment on the new version
            }
            
            response = requests.post(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments",
                json=comment_data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 201:
                logger.warning(f"Failed to add inline comment: {response.text}")
