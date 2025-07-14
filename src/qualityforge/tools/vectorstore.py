"""Vector memory system for Quality Forge using ChromaDB."""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from pydantic import BaseModel

from ..settings import settings
from ..exceptions import QualityForgeError

logger = logging.getLogger(__name__)


class PatchMemory(BaseModel):
    """Represents a stored patch in vector memory."""
    
    id: str
    file_path: str
    original_code: str
    patched_code: str
    patch_content: str
    issues_fixed: List[str]
    quality_improvement: float
    timestamp: str
    success_rate: float = 1.0


class VectorMemory:
    """Vector memory system for caching and retrieving code patches."""
    
    def __init__(self):
        self.db_path = settings.get_vector_db_path()
        self.collection_name = settings.vector_db_collection
        self.client = None
        self.collection = None
        self._initialize_database()
    
    def _initialize_database(self) -> None:
        """Initialize ChromaDB client and collection."""
        try:
            # Ensure the directory exists
            self.db_path.mkdir(parents=True, exist_ok=True)
            
            # Initialize ChromaDB client
            self.client = chromadb.PersistentClient(
                path=str(self.db_path),
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Get or create collection
            try:
                self.collection = self.client.get_collection(self.collection_name)
                logger.info(f"Loaded existing collection: {self.collection_name}")
            except ValueError:
                self.collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"description": "Quality Forge code patches and improvements"}
                )
                logger.info(f"Created new collection: {self.collection_name}")
                
        except Exception as e:
            logger.error(f"Failed to initialize vector database: {e}")
            raise QualityForgeError(f"Vector database initialization failed: {e}")
    
    def store_patch(self, patch_memory: PatchMemory) -> None:
        """Store a successful patch in vector memory."""
        try:
            # Create embedding text from patch content and issues
            embedding_text = f"{patch_memory.patch_content}\nIssues fixed: {', '.join(patch_memory.issues_fixed)}"
            
            # Store in ChromaDB
            self.collection.add(
                documents=[embedding_text],
                metadatas=[{
                    "file_path": patch_memory.file_path,
                    "issues_fixed": patch_memory.issues_fixed,
                    "quality_improvement": patch_memory.quality_improvement,
                    "timestamp": patch_memory.timestamp,
                    "success_rate": patch_memory.success_rate,
                    "patch_content": patch_memory.patch_content
                }],
                ids=[patch_memory.id]
            )
            
            logger.debug(f"Stored patch in vector memory: {patch_memory.id}")
            
        except Exception as e:
            logger.error(f"Failed to store patch in vector memory: {e}")
    
    def find_similar_patches(self, query_text: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Find similar patches based on query text."""
        try:
            if self.collection.count() == 0:
                return []
            
            results = self.collection.query(
                query_texts=[query_text],
                n_results=min(n_results, self.collection.count())
            )
            
            similar_patches = []
            if results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    metadata = results["metadatas"][0][i]
                    distance = results["distances"][0][i] if "distances" in results else 0.0
                    
                    similar_patches.append({
                        "document": doc,
                        "metadata": metadata,
                        "similarity": 1.0 - distance,  # Convert distance to similarity
                        "id": results["ids"][0][i]
                    })
            
            return similar_patches
            
        except Exception as e:
            logger.error(f"Failed to find similar patches: {e}")
            return []
    
    def get_memory_instance(self):
        """Get memory instance for CrewAI integration."""
        # For now, return None as CrewAI memory integration is evolving
        # In the future, this could return a CrewAI-compatible memory instance
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get vector memory statistics."""
        try:
            count = self.collection.count() if self.collection else 0
            return {
                "total_patches": count,
                "collection_name": self.collection_name,
                "db_path": str(self.db_path)
            }
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"error": str(e)}
