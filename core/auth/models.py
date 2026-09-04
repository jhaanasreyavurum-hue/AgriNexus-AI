from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, FrozenSet, Optional


class Role(str, Enum):
    FARMER = "farmer"
    BANK_MANAGER = "bank_manager"
    GOVERNMENT_OFFICER = "government_officer"
    ADMINISTRATOR = "administrator"


ROLE_LABELS: Dict[Role, str] = {
    Role.FARMER: "Farmer",
    Role.BANK_MANAGER: "Bank Manager",
    Role.GOVERNMENT_OFFICER: "Government Officer",
    Role.ADMINISTRATOR: "Administrator",
}


class Permission(str, Enum):
    # farmer
    FARM_ASSESS = "farm:assess"
    FARM_REPORT = "farm:report"
    # bank
    CREDIT_ANALYTICS = "credit:analytics"
    LOAN_PRODUCTS_VIEW = "loan_products:view"
    LOAN_PRODUCTS_MANAGE = "loan_products:manage"
    # government
    SCHEME_ANALYTICS = "scheme:analytics"
    # admin
    USERS_MANAGE = "users:manage"
    REGISTRY_MANAGE = "registry:manage"        # banks / loan schemes / government schemes
    KB_ADMIN = "kb:admin"
    SYSTEM_MONITOR = "system:monitor"


ROLE_PERMISSIONS: Dict[Role, FrozenSet[Permission]] = {
    Role.FARMER: frozenset({Permission.FARM_ASSESS, Permission.FARM_REPORT, Permission.LOAN_PRODUCTS_VIEW}),
    Role.BANK_MANAGER: frozenset({Permission.CREDIT_ANALYTICS, Permission.LOAN_PRODUCTS_VIEW, Permission.LOAN_PRODUCTS_MANAGE}),
    Role.GOVERNMENT_OFFICER: frozenset({Permission.SCHEME_ANALYTICS, Permission.LOAN_PRODUCTS_VIEW}),
    Role.ADMINISTRATOR: frozenset(set(Permission)),
}


class PermissionDenied(PermissionError):
    """Raised by core functions when the acting user lacks the permission."""


@dataclass
class User:
    username: str
    display_name: str
    role: Role
    organisation: str = ""
    farm_id: Optional[str] = None          # farmers: linked demo/user farm
    bank_name: Optional[str] = None        # bank managers
    home_state: Optional[str] = None       # officers / managers default region
    is_demo_account: bool = True
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def role_label(self) -> str:
        return ROLE_LABELS[self.role]

    @property
    def permissions(self) -> FrozenSet[Permission]:
        return ROLE_PERMISSIONS[self.role]

    def can(self, perm: Permission) -> bool:
        return perm in self.permissions

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["role"] = self.role.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "User":
        d = dict(d)
        d["role"] = Role(d["role"])
        return cls(**d)
