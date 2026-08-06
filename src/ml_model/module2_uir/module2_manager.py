"""module2_manager.py.

Orchestration entry point for Module 2 (Unified Intermediate
Representation).

This module contains no parsing, extraction, mapping, schema-building,
or validation logic of its own. It exists solely to run the existing
Module 1 and Module 2 components in the correct order and hand back a
validated Unified Intermediate Representation (UIR):

    Input file
        -> parser_manager.process_iac_file()   (Module 1)
        -> Normalized JSON
        -> uir_schema.build_uir()               (Module 2)
        -> uir_validator.validate_uir()         (Module 2)
        -> Validated UIR

Typical usage:
    from module2_manager import process_to_uir

    uir = process_to_uir("sample_terraform.tf")
    print(uir)
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict

# Relative imports are used since this module lives inside the
# `module2_uir` package alongside its dependencies, and reaches across
# to the sibling `module1_iac_parser` package for Module 1's entry
# point. A fallback to absolute imports is provided so the module also
# runs correctly when executed directly as a script (e.g.
# `python module2_manager.py sample_terraform.tf`), where Python has no
# enclosing package context for relative imports to resolve against.
try:
    from .uir_schema import UIRSchemaError, build_uir
    from .uir_validator import UIRValidationError, validate_uir
    from ..module1_iac_parser.parser_manager import (
        ParserManagerError,
        process_iac_file,
    )
except ImportError:
    from uir_schema import UIRSchemaError, build_uir  # type: ignore[no-redef]
    from uir_validator import UIRValidationError, validate_uir  # type: ignore[no-redef]
    from parser_manager import (  # type: ignore[no-redef]
        ParserManagerError,
        process_iac_file,
    )

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

if not logger.handlers:
    # Configure a default handler only if the module is used standalone
    # (i.e. the host application hasn't already configured logging).
    _handler = logging.StreamHandler()
    _formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------
class Module2ManagerError(Exception):
    """Wraps unexpected internal failures raised while orchestrating Module 2.

    Known, already-specific exceptions raised by the lower-level
    modules this manager orchestrates (`ParserManagerError`,
    `UIRSchemaError`, `UIRValidationError`) are re-raised unchanged and
    are never wrapped in this exception. `Module2ManagerError` is
    reserved strictly for failures this manager did not anticipate.
    """


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------
def process_to_uir(file_path: str) -> Dict[str, Any]:
    """Run the full Module 1 + Module 2 pipeline and return a validated UIR.

    This is the sole public entry point of Module 2. It performs, in
    order:
        1. Parsing and normalization, via
           `parser_manager.process_iac_file()` (Module 1).
        2. UIR construction, via `uir_schema.build_uir()`.
        3. UIR validation, via `uir_validator.validate_uir()`.

    Args:
        file_path: Path to the Terraform (.tf) or CloudFormation
            (.yaml, .yml, .json) file to process.

    Returns:
        The validated UIR dictionary produced by `build_uir()`, with
        the shape:
            {
                "provider": "...",
                "metadata": {
                    "resource_count": ...,
                    "dependency_count": ...
                },
                "resources": [...],
                "dependencies": [...]
            }

    Raises:
        ParserManagerError: If Module 1 fails to parse, extract, or
            normalize the input file.
        UIRSchemaError: If `build_uir()` cannot construct a valid UIR
            from the normalized JSON.
        UIRValidationError: If the constructed UIR fails schema
            validation.
        Module2ManagerError: If any other, unanticipated failure occurs
            while orchestrating the pipeline.
    """
    logger.info("Starting Module 2 for file: %s", file_path)

    try:
        normalized_json = process_iac_file(file_path)

        logger.info("Building UIR for file: %s", file_path)
        uir = build_uir(normalized_json)

        logger.info("Validating UIR for file: %s", file_path)
        validate_uir(uir)

        logger.info("Completed Module 2 for file: %s", file_path)
        return uir

    except (ParserManagerError, UIRSchemaError, UIRValidationError) as exc:
        logger.error("Module 2 failed for file %s: %s", file_path, exc)
        raise

    except Exception as exc:
        logger.error("Unexpected error in Module 2 for file %s: %s", file_path, exc)
        raise Module2ManagerError(
            f"Unexpected failure while processing file: {file_path}"
        ) from exc


# ---------------------------------------------------------------------------
# Script entry point (manual/local testing convenience)
# ---------------------------------------------------------------------------
def main() -> None:
    """Run `process_to_uir()` from the command line and pretty-print the result.

    Usage:
        python module2_manager.py <path_to_tf_or_cfn_file>
    """
    if len(sys.argv) != 2:
        logger.error("Usage: python module2_manager.py <path_to_tf_or_cfn_file>")
        sys.exit(1)

    file_path = sys.argv[1]

    try:
        uir = process_to_uir(file_path)
        print(json.dumps(uir, indent=4))
    except (ParserManagerError, UIRSchemaError, UIRValidationError, Module2ManagerError) as exc:
        logger.error("Module 2 processing failed: %s", exc)
        sys.exit(1)


__all__ = [
    "Module2ManagerError",
    "process_to_uir",
]


if __name__ == "__main__":
    main()
