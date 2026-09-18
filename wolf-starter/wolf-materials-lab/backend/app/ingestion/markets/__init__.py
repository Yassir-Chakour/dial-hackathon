"""Markets package registering all country-specific capability rules."""

from app.ingestion.markets.france import FranceMarketRules, france_rules_instance
from app.ingestion.markets.hungary import HungaryMarketRules, hungary_rules_instance
from app.ingestion.markets.italy import ItalyMarketRules, italy_rules_instance
from app.ingestion.markets.kosovo import KosovoMarketRules, kosovo_rules_instance

__all__ = [
    "FranceMarketRules",
    "france_rules_instance",
    "ItalyMarketRules",
    "italy_rules_instance",
    "HungaryMarketRules",
    "hungary_rules_instance",
    "KosovoMarketRules",
    "kosovo_rules_instance",
]
