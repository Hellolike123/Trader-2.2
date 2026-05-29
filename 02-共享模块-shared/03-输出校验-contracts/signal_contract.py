"""Re-export stub — signal_contract has moved to trader_shared.signal_contract."""
from trader_shared.signal_contract import *  # noqa: F401,F403
from trader_shared.signal_contract import (
    CONTRACT_VERSION, REQUIRED_FIELDS, ALLOWED_SOURCE_SKILLS,
    ALLOWED_SIGNAL_TYPES, ALLOWED_DIRECTIONS, ALLOWED_ACTIONS,
    ALLOWED_CONFIDENCE, ALLOWED_DATA_STATUS,
    normalize_signal, validate_signal, assert_valid_signal,
)
