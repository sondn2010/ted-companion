"""Compatibility wrapper for legacy hermes_json_contract_request imports."""
from src.bridge.openai_json_contract_request import (
    OpenAIContractError as HermesContractError,
    extract_json_block,
    request_openai_json_contract as request_json,
)

__all__ = ["HermesContractError", "extract_json_block", "request_json"]
