import os
import threading
from pathlib import Path
from typing import Dict, List, Tuple

from app.services.ai.FieldOpsAI.schemas.prompt_metadata import PromptMetadata, PromptType
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask

class SafePromptError(Exception):
    pass

class PromptRegistryError(SafePromptError):
    pass

class PromptRegistrationError(PromptRegistryError):
    pass

class PromptNotFoundError(PromptRegistryError):
    pass

class PromptFileError(PromptRegistryError):
    pass

class PromptTemplateRegistry:
    def __init__(self, prompt_root: Path, max_prompt_bytes: int = 1024 * 1024):
        try:
            self._prompt_root = Path(prompt_root).resolve()
        except Exception:
            raise PromptRegistryError("Invalid prompt root path") from None
            
        if not self._prompt_root.exists():
            raise PromptRegistryError("Prompt root does not exist")
        if not self._prompt_root.is_dir():
            raise PromptRegistryError("Prompt root is not a directory")
            
        if isinstance(max_prompt_bytes, bool) or not isinstance(max_prompt_bytes, int) or max_prompt_bytes <= 0:
            raise PromptRegistryError("max_prompt_bytes must be a positive integer")
            
        self._max_prompt_bytes = max_prompt_bytes
        self._registry: Dict[str, PromptMetadata] = {}
        self._task_mapping: Dict[AITask, str] = {}
        self._system_order: List[str] = []
        self._cache: Dict[str, str] = {}
        self._lock = threading.RLock()

    def _resolve_and_read(self, metadata: PromptMetadata) -> str:
        candidate_path = (self._prompt_root / metadata.relative_path).resolve()
        
        try:
            # Use os.path.commonpath to ensure candidate_path is under self._prompt_root
            if os.path.commonpath([str(self._prompt_root), str(candidate_path)]) != str(self._prompt_root):
                raise PromptFileError("Path traversal detected.")
        except ValueError:
            raise PromptFileError("Invalid path resolution.")
        
        if not candidate_path.exists():
            raise PromptFileError("Prompt file does not exist.")
        if not candidate_path.is_file():
            raise PromptFileError("Prompt path is not a regular file.")
        
        try:
            file_size = candidate_path.stat().st_size
        except OSError:
            raise PromptFileError("Failed to access prompt file.")
            
        if file_size == 0:
            raise PromptFileError("Prompt file is empty.")
        if file_size > self._max_prompt_bytes:
            raise PromptFileError("Prompt file exceeds maximum allowed size.")

        try:
            text = candidate_path.read_text(encoding="utf-8")
            if not text.strip():
                raise PromptFileError("Prompt file is empty or whitespace-only.")
            return text.strip()
        except UnicodeDecodeError:
            raise PromptFileError("Prompt file is not valid UTF-8.")
        except PromptFileError:
            raise
        except Exception:
            raise PromptFileError("Failed to read prompt file.") from None

    def register(self, metadata: PromptMetadata) -> None:
        with self._lock:
            if metadata.key in self._registry:
                raise PromptRegistrationError(f"Duplicate prompt key: {metadata.key}")
            if metadata.prompt_type == PromptType.TASK and metadata.task in self._task_mapping:
                raise PromptRegistrationError(f"Duplicate task registration: {metadata.task.value}")

            text = self._resolve_and_read(metadata)

            self._registry[metadata.key] = metadata
            self._cache[metadata.key] = text
            if metadata.prompt_type == PromptType.TASK and metadata.task:
                self._task_mapping[metadata.task] = metadata.key
            elif metadata.prompt_type == PromptType.SYSTEM:
                self._system_order.append(metadata.key)

    def get_text(self, key: str) -> str:
        """
        Direct/administrative lookup of prompt text.
        Returns the text even if the prompt is disabled.
        """
        if not key or not str(key).strip():
            raise PromptNotFoundError("Blank prompt key.")
            
        normalized_key = str(key).strip().upper()
            
        with self._lock:
            if normalized_key not in self._registry:
                raise PromptNotFoundError(f"Unknown prompt key: {normalized_key}")
            
            if normalized_key in self._cache:
                return self._cache[normalized_key]
            
            metadata = self._registry[normalized_key]
            text = self._resolve_and_read(metadata)
            self._cache[normalized_key] = text
            return text

    def get_task_prompt(self, task: AITask) -> str:
        if not isinstance(task, AITask):
            raise PromptNotFoundError("Invalid task type.")
            
        with self._lock:
            key = self._task_mapping.get(task)
            if not key:
                raise PromptNotFoundError("Task not registered.")
                
            metadata = self._registry[key]
            if not metadata.enabled:
                raise PromptNotFoundError("Task prompt is disabled.")
                
            return self.get_text(key)

    def get_system_instructions(self) -> Tuple[str, ...]:
        with self._lock:
            instructions = []
            for key in self._system_order:
                metadata = self._registry[key]
                if metadata.enabled:
                    instructions.append(self.get_text(key))
            return tuple(instructions)

    def list_registered(self) -> Tuple[PromptMetadata, ...]:
        with self._lock:
            # Deterministic order based on key
            return tuple(self._registry[k] for k in sorted(self._registry.keys()))

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()


_default_registry = None
_registry_lock = threading.Lock()

def get_default_prompt_registry() -> PromptTemplateRegistry:
    global _default_registry
    with _registry_lock:
        if _default_registry is None:
            root = Path(__file__).resolve().parent.parent
            registry = PromptTemplateRegistry(prompt_root=root)
            
            system_prompts = [
                ("IDENTITY", "IDENTITY.md"),
                ("SOUL", "SOUL.md"),
                ("RULES", "knowledge/business_rules.md"),
                ("LIFECYCLE", "knowledge/lifecycle.md"),
                ("ROLES", "knowledge/roles.md"),
                ("VALIDATION", "knowledge/validation.md"),
            ]
            for key, path in system_prompts:
                registry.register(PromptMetadata(
                    key=key,
                    relative_path=path,
                    prompt_type=PromptType.SYSTEM
                ))
            
            task_prompts = [
                ("TASK_PLANNING", "prompts/planning.md", AITask.PLANNING),
                ("TASK_DISPATCH", "prompts/dispatch.md", AITask.DISPATCH),
                ("TASK_MONITORING", "prompts/monitoring.md", AITask.MONITORING),
                ("TASK_SENTIMENT", "prompts/sentiment.md", AITask.SENTIMENT),
                ("TASK_COMMUNICATION", "prompts/communication.md", AITask.COMMUNICATION),
                ("TASK_CLOSURE", "prompts/closure.md", AITask.CLOSURE),
                ("TASK_INTENT", "prompts/intent.md", AITask.INTENT),
                ("TASK_INTAKE", "prompts/intake.md", AITask.INTAKE),
            ]
            for key, path, task in task_prompts:
                registry.register(PromptMetadata(
                    key=key,
                    relative_path=path,
                    prompt_type=PromptType.TASK,
                    task=task
                ))
            
            _default_registry = registry
    return _default_registry
