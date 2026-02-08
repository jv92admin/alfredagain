"""
Root pytest configuration.

Environment setup is shared. Domain-specific fixtures live in
tests/core/conftest.py (StubDomainConfig) and tests/kitchen/conftest.py (KITCHEN_DOMAIN).
"""

import os

# Set test environment before importing alfred modules
os.environ["ALFRED_ENV"] = "development"
os.environ["ALFRED_USE_ADVANCED_MODELS"] = "false"
