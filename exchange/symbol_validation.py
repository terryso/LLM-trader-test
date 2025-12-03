"""
Symbol validation service for different exchange backends.

This module provides symbol validation functionality that respects the
MARKET_DATA_BACKEND configuration. It centralizes all backend-specific
validation logic in the exchange layer (not config layer) and provides:

- Client singleton reuse to avoid repeated initialization
- Symbol-level TTL cache to reduce API calls
- Clear separation between "symbol not found" and "backend error" semantics
- Public API that doesn't expose internal implementation details

Story 9.3: 基于 MARKET_DATA_BACKEND 的 symbol 校验
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

from binance.client import Client

from config.settings import BACKPACK_API_BASE_URL
from exchange.market_data import BackpackMarketDataClient, BinanceMarketDataClient


class ValidationErrorType(Enum):
    """Error type classification for symbol validation."""
    
    NONE = "none"  # No error, validation successful
    SYMBOL_NOT_FOUND = "symbol_not_found"  # Symbol doesn't exist on backend
    NETWORK_ERROR = "network_error"  # Network/connection issues
    API_ERROR = "api_error"  # Backend API returned error
    UNKNOWN_BACKEND = "unknown_backend"  # Backend type not supported


@dataclass
class ValidationResult:
    """Result of symbol validation with semantic error classification."""
    
    is_valid: bool
    error_type: ValidationErrorType
    error_message: str
    backend: str
    
    def to_tuple(self) -> Tuple[bool, str]:
        """Convert to legacy (is_valid, error_message) tuple format."""
        return (self.is_valid, self.error_message)


@dataclass
class _CacheEntry:
    """Cache entry for symbol validation results."""
    
    result: ValidationResult
    timestamp: float


class SymbolValidationService:
    """
    Centralized symbol validation service with caching and client reuse.
    
    This service:
    - Maintains singleton clients for each backend to avoid repeated initialization
    - Caches validation results with configurable TTL
    - Provides clear error semantics distinguishing "not found" from "backend error"
    - Thread-safe for concurrent access
    """
    
    # Default cache TTL in seconds (5 minutes)
    DEFAULT_CACHE_TTL = 300.0
    
    def __init__(self, cache_ttl: float = DEFAULT_CACHE_TTL) -> None:
        self._cache_ttl = cache_ttl
        self._cache: Dict[Tuple[str, str], _CacheEntry] = {}
        self._lock = threading.Lock()
        
        # Lazy-initialized clients (singleton per backend)
        self._binance_client: Optional[BinanceMarketDataClient] = None
        self._backpack_client: Optional[BackpackMarketDataClient] = None
    
    def _get_binance_client(self) -> BinanceMarketDataClient:
        """Get or create singleton Binance market data client."""
        if self._binance_client is None:
            # Use empty credentials for public endpoints (symbol validation)
            binance_raw = Client("", "")
            self._binance_client = BinanceMarketDataClient(binance_raw)
        return self._binance_client
    
    def _get_backpack_client(self) -> BackpackMarketDataClient:
        """Get or create singleton Backpack market data client."""
        if self._backpack_client is None:
            self._backpack_client = BackpackMarketDataClient(BACKPACK_API_BASE_URL)
        return self._backpack_client
    
    def _get_cached(self, backend: str, symbol: str) -> Optional[ValidationResult]:
        """Get cached validation result if still valid."""
        cache_key = (backend, symbol)
        with self._lock:
            entry = self._cache.get(cache_key)
            if entry is None:
                return None
            if time.time() - entry.timestamp > self._cache_ttl:
                # Cache expired
                del self._cache[cache_key]
                return None
            return entry.result
    
    def _set_cached(self, backend: str, symbol: str, result: ValidationResult) -> None:
        """Cache a validation result."""
        cache_key = (backend, symbol)
        with self._lock:
            self._cache[cache_key] = _CacheEntry(result=result, timestamp=time.time())
    
    def clear_cache(self) -> None:
        """Clear all cached validation results."""
        with self._lock:
            self._cache.clear()
    
    def validate_symbol_binance(self, symbol: str) -> ValidationResult:
        """
        Validate symbol against Binance Futures market data.
        
        Uses a lightweight klines request to verify the symbol exists.
        Distinguishes between "symbol not found" and "network/API error".
        
        Args:
            symbol: Normalized symbol (e.g., "BTCUSDT").
            
        Returns:
            ValidationResult with semantic error classification.
        """
        backend = "binance"
        
        # Check cache first
        cached = self._get_cached(backend, symbol)
        if cached is not None:
            return cached
        
        try:
            client = self._get_binance_client()
            klines = client.get_klines(symbol, "1m", 1)
            
            if klines and len(klines) > 0:
                result = ValidationResult(
                    is_valid=True,
                    error_type=ValidationErrorType.NONE,
                    error_message="",
                    backend=backend,
                )
            else:
                result = ValidationResult(
                    is_valid=False,
                    error_type=ValidationErrorType.SYMBOL_NOT_FOUND,
                    error_message=f"Symbol '{symbol}' 不被当前 backend 支持 (backend: {backend})",
                    backend=backend,
                )
            
            self._set_cached(backend, symbol, result)
            return result
            
        except Exception as exc:
            error_msg = str(exc)
            lower = error_msg.lower()
            
            # Classify error type based on error message patterns
            if "invalid symbol" in lower:
                # This is a "symbol not found" error from Binance
                logging.info(
                    "Symbol validation failed for %s on binance: %s", symbol, error_msg
                )
                result = ValidationResult(
                    is_valid=False,
                    error_type=ValidationErrorType.SYMBOL_NOT_FOUND,
                    error_message=f"Symbol '{symbol}' 不被当前 backend 支持 (backend: {backend})",
                    backend=backend,
                )
            elif "timeout" in lower or "connection" in lower:
                # Network error - don't cache, might be transient
                logging.warning(
                    "Binance network error for symbol %s: %s", symbol, error_msg
                )
                return ValidationResult(
                    is_valid=False,
                    error_type=ValidationErrorType.NETWORK_ERROR,
                    error_message=f"Symbol '{symbol}' 校验失败: 网络错误 (backend: {backend}, error: {error_msg})",
                    backend=backend,
                )
            else:
                # Other API errors
                logging.warning(
                    "Binance symbol validation error for %s: %s", symbol, error_msg
                )
                result = ValidationResult(
                    is_valid=False,
                    error_type=ValidationErrorType.API_ERROR,
                    error_message=f"Symbol '{symbol}' 校验失败 (backend: {backend}, error: {error_msg})",
                    backend=backend,
                )
            
            # Cache "symbol not found" errors, but not network errors
            if result.error_type == ValidationErrorType.SYMBOL_NOT_FOUND:
                self._set_cached(backend, symbol, result)
            
            return result
    
    def validate_symbol_backpack(self, symbol: str) -> ValidationResult:
        """
        Validate symbol against Backpack exchange market data.
        
        Uses the symbol_exists() public method to verify the symbol exists.
        Handles symbol normalization from BTCUSDT to BTC_USDC_PERP format.
        Distinguishes between "symbol not found" and "network/API error".
        
        Args:
            symbol: Normalized symbol (e.g., "BTCUSDT").
            
        Returns:
            ValidationResult with semantic error classification.
        """
        backend = "backpack"
        
        # Check cache first
        cached = self._get_cached(backend, symbol)
        if cached is not None:
            return cached
        
        try:
            client = self._get_backpack_client()
            
            # Use public method instead of private _normalize_symbol
            exists, normalized_symbol, error_info = client.symbol_exists(symbol)
            
            if exists:
                result = ValidationResult(
                    is_valid=True,
                    error_type=ValidationErrorType.NONE,
                    error_message="",
                    backend=backend,
                )
                self._set_cached(backend, symbol, result)
                return result
            
            # Distinguish between backend errors and symbol not found
            if error_info:
                lower = error_info.lower()
                if "network" in lower or "timeout" in lower or "connection" in lower:
                    # Network error - don't cache
                    logging.warning(
                        "Backpack network error for symbol %s: %s", symbol, error_info
                    )
                    return ValidationResult(
                        is_valid=False,
                        error_type=ValidationErrorType.NETWORK_ERROR,
                        error_message=f"Symbol '{symbol}' 校验失败: 网络错误 (backend: {backend}, error: {error_info})",
                        backend=backend,
                    )
                # Backend/API error - don't cache
                logging.warning(
                    "Backpack API error for symbol %s: %s", symbol, error_info
                )
                return ValidationResult(
                    is_valid=False,
                    error_type=ValidationErrorType.API_ERROR,
                    error_message=f"Symbol '{symbol}' 校验失败 (backend: {backend}, error: {error_info})",
                    backend=backend,
                )

            # Symbol not found (no error_info)
            result = ValidationResult(
                is_valid=False,
                error_type=ValidationErrorType.SYMBOL_NOT_FOUND,
                error_message=(
                    f"Symbol '{symbol}' (Backpack: {normalized_symbol}) "
                    f"在 Backpack 对应 USDC 合约列表中未找到 (backend: {backend})"
                ),
                backend=backend,
            )
            self._set_cached(backend, symbol, result)
            return result
            
        except Exception as exc:
            error_msg = str(exc)
            logging.warning(
                "Backpack symbol validation error for %s: %s", symbol, error_msg
            )
            # Don't cache unexpected errors
            return ValidationResult(
                is_valid=False,
                error_type=ValidationErrorType.API_ERROR,
                error_message=f"Symbol '{symbol}' 校验失败 (backend: {backend}, error: {error_msg})",
                backend=backend,
            )
    
    def validate_symbol(self, symbol: str, backend: str) -> ValidationResult:
        """
        Validate symbol for the specified backend.
        
        Args:
            symbol: Symbol to validate (e.g., "BTCUSDT").
            backend: Backend type ("binance" or "backpack").
            
        Returns:
            ValidationResult with semantic error classification.
        """
        if backend == "binance":
            return self.validate_symbol_binance(symbol)
        elif backend == "backpack":
            return self.validate_symbol_backpack(symbol)
        else:
            logging.warning(
                "Unknown MARKET_DATA_BACKEND '%s' for symbol validation. "
                "TODO: Add validation support for this backend.", backend
            )
            return ValidationResult(
                is_valid=False,
                error_type=ValidationErrorType.UNKNOWN_BACKEND,
                error_message=(
                    f"Symbol '{symbol}' 无法校验: 未知的 backend '{backend}' "
                    f"(TODO: 需要为此 backend 添加校验支持)"
                ),
                backend=backend,
            )


# Global singleton instance for the validation service
_validation_service: Optional[SymbolValidationService] = None
_service_lock = threading.Lock()


def get_validation_service() -> SymbolValidationService:
    """Get the global singleton validation service instance."""
    global _validation_service
    if _validation_service is None:
        with _service_lock:
            if _validation_service is None:
                _validation_service = SymbolValidationService()
    return _validation_service


def validate_symbol_for_backend(symbol: str, backend: str) -> Tuple[bool, str]:
    """
    Validate symbol for the specified backend.
    
    This is the main entry point for symbol validation from other modules.
    Uses the singleton validation service with caching.
    
    This function is defensive: it never raises exceptions and always
    returns a (is_valid, error_message) tuple, even if the underlying
    service encounters unexpected errors.
    
    Args:
        symbol: Symbol to validate (e.g., "BTCUSDT").
        backend: Backend type ("binance" or "backpack").
        
    Returns:
        Tuple of (is_valid, error_message).
    """
    try:
        service = get_validation_service()
        result = service.validate_symbol(symbol, backend)
        return result.to_tuple()
    except Exception as exc:  # pragma: no cover - defensive guardrail
        logging.warning(
            "Symbol validation internal error for %s on %s: %s", symbol, backend, exc
        )
        return (
            False,
            f"Symbol '{symbol}' 校验失败 (backend: {backend}, error: internal error: {exc})",
        )
