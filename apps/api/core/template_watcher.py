"""
Template watcher and cache manager for hot-reloading bank templates.
Monitors file system for changes and maintains in-memory cache.
"""
import os
import threading
from pathlib import Path
from typing import Dict, Optional, Callable, List
from datetime import datetime
import logging
import yaml
from collections import defaultdict

logger = logging.getLogger(__name__)

BANK_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "packages" / "bank-templates"


class BankTemplateCache:
    """In-memory cache for bank templates with thread safety."""
    
    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._lock = threading.RLock()
        self._load_times: Dict[str, datetime] = {}
        self._stats = {
            "hits": 0,
            "misses": 0,
            "reloads": 0,
            "errors": 0,
        }
    
    def get(self, bank_code: str) -> Optional[Dict]:
        """Get template from cache."""
        with self._lock:
            if bank_code in self._cache:
                self._stats["hits"] += 1
                return self._cache[bank_code].copy()
            self._stats["misses"] += 1
            return None
    
    def set(self, bank_code: str, template: Dict) -> None:
        """Set template in cache."""
        with self._lock:
            self._cache[bank_code] = template.copy()
            self._load_times[bank_code] = datetime.now()
            self._stats["reloads"] += 1
    
    def delete(self, bank_code: str) -> None:
        """Remove template from cache."""
        with self._lock:
            self._cache.pop(bank_code, None)
            self._load_times.pop(bank_code, None)
    
    def clear(self) -> None:
        """Clear all cache."""
        with self._lock:
            self._cache.clear()
            self._load_times.clear()
            logger.info("Template cache cleared")
    
    def list_all(self) -> Dict[str, Dict]:
        """Get all cached templates."""
        with self._lock:
            return {k: v.copy() for k, v in self._cache.items()}
    
    def get_stats(self) -> Dict:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                "total_cached": len(self._cache),
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "reloads": self._stats["reloads"],
                "errors": self._stats["errors"],
                "hit_rate": round(hit_rate, 2),
                "cached_banks": list(self._cache.keys()),
                "last_loaded": {k: v.isoformat() for k, v in self._load_times.items()},
            }
    
    def increment_errors(self) -> None:
        """Increment error counter."""
        with self._lock:
            self._stats["errors"] += 1


class TemplateWatcher:
    """Watch for template file changes and trigger reloads."""
    
    def __init__(self, cache: BankTemplateCache):
        self.cache = cache
        self._file_mtimes: Dict[str, float] = {}
        self._callbacks: List[Callable] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def add_listener(self, callback: Callable) -> None:
        """Add change listener callback."""
        self._callbacks.append(callback)
    
    def start(self) -> None:
        """Start watching for template changes."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info("Template watcher started")
    
    def stop(self) -> None:
        """Stop watching for changes."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Template watcher stopped")
    
    def _watch_loop(self) -> None:
        """Main watch loop - monitors file system."""
        while self._running:
            try:
                self._check_for_changes()
                threading.Event().wait(1)  # Check every 1 second
            except Exception as e:
                logger.error(f"Error in watch loop: {e}")
    
    def _check_for_changes(self) -> None:
        """Check for file changes and reload if needed."""
        if not BANK_TEMPLATES_DIR.exists():
            return
        
        for template_file in BANK_TEMPLATES_DIR.glob("*.yaml"):
            bank_code = template_file.stem.lower()
            
            try:
                mtime = template_file.stat().st_mtime
                
                if bank_code not in self._file_mtimes:
                    # New file
                    self._file_mtimes[bank_code] = mtime
                    self._reload_template(bank_code, template_file)
                    self._notify_change("added", bank_code)
                
                elif self._file_mtimes[bank_code] != mtime:
                    # File modified
                    self._file_mtimes[bank_code] = mtime
                    self._reload_template(bank_code, template_file)
                    self._notify_change("modified", bank_code)
            
            except OSError as e:
                logger.error(f"Error checking file {template_file}: {e}")
        
        # Check for deleted files
        deleted_banks = []
        for bank_code in list(self._file_mtimes.keys()):
            template_file = BANK_TEMPLATES_DIR / f"{bank_code}.yaml"
            if not template_file.exists():
                deleted_banks.append(bank_code)
                del self._file_mtimes[bank_code]
                self.cache.delete(bank_code)
                self._notify_change("deleted", bank_code)
    
    def _reload_template(self, bank_code: str, template_file: Path) -> None:
        """Reload a single template file."""
        try:
            with open(template_file, 'r') as f:
                template_data = yaml.safe_load(f)
            
            if template_data:
                self.cache.set(bank_code, template_data)
                logger.info(f"Reloaded template: {bank_code}")
        except Exception as e:
            logger.error(f"Error reloading template {bank_code}: {e}")
            self.cache.increment_errors()
    
    def _notify_change(self, action: str, bank_code: str) -> None:
        """Notify listeners of template change."""
        for callback in self._callbacks:
            try:
                callback(action=action, bank_code=bank_code)
            except Exception as e:
                logger.error(f"Error in change callback: {e}")
    
    def force_reload_all(self) -> Dict[str, bool]:
        """Force reload all templates from disk."""
        results = {}
        if not BANK_TEMPLATES_DIR.exists():
            return results
        
        for template_file in BANK_TEMPLATES_DIR.glob("*.yaml"):
            bank_code = template_file.stem.lower()
            try:
                with open(template_file, 'r') as f:
                    template_data = yaml.safe_load(f)
                
                if template_data:
                    self.cache.set(bank_code, template_data)
                    results[bank_code] = True
                    logger.info(f"Force reloaded: {bank_code}")
            except Exception as e:
                results[bank_code] = False
                logger.error(f"Error force reloading {bank_code}: {e}")
        
        return results
    
    def force_reload_bank(self, bank_code: str) -> bool:
        """Force reload a specific template."""
        template_file = BANK_TEMPLATES_DIR / f"{bank_code.lower()}.yaml"
        
        if not template_file.exists():
            logger.warning(f"Template file not found: {template_file}")
            return False
        
        try:
            with open(template_file, 'r') as f:
                template_data = yaml.safe_load(f)
            
            if template_data:
                self.cache.set(bank_code, template_data)
                mtime = template_file.stat().st_mtime
                self._file_mtimes[bank_code.lower()] = mtime
                logger.info(f"Force reloaded: {bank_code}")
                return True
        except Exception as e:
            logger.error(f"Error force reloading {bank_code}: {e}")
            return False


class TemplateManager:
    """High-level template manager combining cache and watcher."""
    
    def __init__(self):
        self.cache = BankTemplateCache()
        self.watcher = TemplateWatcher(self.cache)
    
    def initialize(self) -> None:
        """Initialize the template system."""
        # Load all existing templates into cache
        self._load_initial_templates()
        # Start file system watcher
        self.watcher.start()
        logger.info("Template manager initialized")
    
    def shutdown(self) -> None:
        """Shutdown the template system."""
        self.watcher.stop()
        logger.info("Template manager shutdown")
    
    def _load_initial_templates(self) -> None:
        """Load all existing templates on startup."""
        if not BANK_TEMPLATES_DIR.exists():
            return
        
        for template_file in BANK_TEMPLATES_DIR.glob("*.yaml"):
            bank_code = template_file.stem.lower()
            try:
                with open(template_file, 'r') as f:
                    template_data = yaml.safe_load(f)
                
                if template_data:
                    self.cache.set(bank_code, template_data)
                    mtime = template_file.stat().st_mtime
                    self.watcher._file_mtimes[bank_code] = mtime
            except Exception as e:
                logger.error(f"Error loading initial template {bank_code}: {e}")
    
    def get_template(self, bank_code: str) -> Optional[Dict]:
        """Get a template (from cache)."""
        return self.cache.get(bank_code.lower())
    
    def list_templates(self) -> Dict[str, Dict]:
        """List all cached templates."""
        return self.cache.list_all()
    
    def reload_all(self) -> Dict[str, bool]:
        """Force reload all templates."""
        return self.watcher.force_reload_all()
    
    def reload_bank(self, bank_code: str) -> bool:
        """Force reload a specific bank."""
        return self.watcher.force_reload_bank(bank_code)
    
    def get_stats(self) -> Dict:
        """Get cache statistics."""
        return self.cache.get_stats()
    
    def clear_cache(self) -> None:
        """Clear all cache."""
        self.cache.clear()
    
    def add_listener(self, callback: Callable) -> None:
        """Add change listener."""
        self.watcher.add_listener(callback)


# Global template manager instance
_template_manager: Optional[TemplateManager] = None


def get_template_manager() -> TemplateManager:
    """Get or create the global template manager."""
    global _template_manager
    if _template_manager is None:
        _template_manager = TemplateManager()
    return _template_manager


def initialize_template_manager() -> None:
    """Initialize the global template manager."""
    get_template_manager().initialize()


def shutdown_template_manager() -> None:
    """Shutdown the global template manager."""
    get_template_manager().shutdown()
