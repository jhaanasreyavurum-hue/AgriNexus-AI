"""Plain financial arithmetic (EMI, amortisation, product comparison). Deterministic, no KB."""
from .emi import EMIResult, emi, amortisation_schedule, compare_products

__all__ = ["EMIResult", "emi", "amortisation_schedule", "compare_products"]
